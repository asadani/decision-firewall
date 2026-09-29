"""Loopback-only inspection and review of the simulated refund workflow."""

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .contracts import ReviewDecision
from .engine import Firewall, FirewallError


def create_app(home=Path(".runtime"), runs=Path("runs")):
    fw = Firewall(home)
    assets = Path(__file__).parent
    templates = Jinja2Templates(directory=assets / "templates")
    templates.env.filters["money"] = lambda value: f"INR {value / 100:,.2f}"
    templates.env.filters["time"] = lambda value: datetime.fromtimestamp(value, UTC).strftime(
        "%d %b %Y · %H:%M:%S UTC"
    )
    app = FastAPI(title="Decision Firewall — local simulator", docs_url=None, redoc_url=None)
    secret_file = Path(home) / "session.key"
    if not secret_file.exists():
        try:
            with secret_file.open("x") as file:
                file.write(secrets.token_hex(32))
            secret_file.chmod(0o600)
        except FileExistsError:
            pass
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_file.read_text(),
        same_site="strict",
        session_cookie="firewall_local",
        max_age=3600,
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )
    app.mount("/static", StaticFiles(directory=assets / "static"), name="static")
    app.state.firewall = fw

    @app.middleware("http")
    async def headers(request, call_next):
        if (
            request.headers.get("host", "").split(":")[0] == "testserver"
            and request.client
            and request.client.host != "testclient"
        ):
            return HTMLResponse("Invalid host", status_code=400)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def render(request, template, **context):
        request.session.setdefault("csrf", secrets.token_urlsafe(32))
        return templates.TemplateResponse(
            request=request, name=template, context={"csrf": request.session["csrf"], **context}
        )

    @app.exception_handler(FirewallError)
    async def domain_error(request, exc):
        response = render(request, "error.html", title="Request unavailable", error=str(exc))
        response.status_code = 404 if str(exc) == "Request not found" else 409
        return response

    @app.exception_handler(404)
    async def not_found(request, exc):
        response = render(
            request,
            "error.html",
            title="Page not found",
            error="This page does not exist. Return to the request list.",
        )
        response.status_code = 404
        return response

    @app.get("/")
    def index(request: Request, q: str = "", status: str = "", page: int = 1):
        data = fw.list_requests(q, status, page)
        links = {
            "previous": "/?" + urlencode({"q": q, "status": status, "page": data["page"] - 1}),
            "next": "/?" + urlencode({"q": q, "status": status, "page": data["page"] + 1}),
        }
        return render(
            request,
            "list.html",
            title="Refund requests",
            data=data,
            q=q,
            status=status,
            links=links,
            review=False,
        )

    @app.get("/reviews")
    def reviews(request: Request, page: int = 1):
        data = fw.list_requests(status="REQUIRE_REVIEW", page=page)
        return render(
            request,
            "list.html",
            title="Review queue",
            data=data,
            q="",
            status="REQUIRE_REVIEW",
            review=True,
            links={
                "previous": f"/reviews?page={data['page'] - 1}",
                "next": f"/reviews?page={data['page'] + 1}",
            },
        )

    @app.get("/requests/{rid}")
    def detail(request: Request, rid: str, saved: bool = False):
        return render(
            request,
            "detail.html",
            title="Decision detail",
            item=fw.detail(rid),
            saved=saved,
            error=None,
            reason="",
        )

    @app.post("/requests/{rid}/review")
    async def review(request: Request, rid: str):
        form = await request.form()
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host')}"
        if (
            not origin
            or not request.session.get("csrf")
            or origin != expected
            or urlsplit(origin).hostname not in {"127.0.0.1", "localhost", "testserver"}
            or not secrets.compare_digest(
                str(form.get("csrf", "")), request.session.get("csrf", "")
            )
        ):
            response = render(
                request,
                "error.html",
                title="Review not saved",
                error="Session or origin check failed. Reload the request and try again.",
            )
            response.status_code = 403
            return response
        try:
            decision = ReviewDecision.model_validate(
                {
                    "decision": str(form.get("decision", "")),
                    "reason": str(form.get("reason", "")),
                }
            )
            revision = int(str(form.get("revision", "0")))
            fw.review(rid, decision, revision)
        except (ValueError, ValidationError) as exc:
            response = render(
                request,
                "detail.html",
                title="Review not saved",
                item=fw.detail(rid),
                saved=False,
                error=str(exc),
                reason=str(form.get("reason", "")),
            )
            response.status_code = 409 if isinstance(exc, FirewallError) else 422
            return response
        return RedirectResponse(f"/requests/{rid}?saved=true", status_code=303)

    @app.get("/requests/{rid}/receipt")
    def receipt(rid: str):
        fw.detail(rid)
        # A complete chain permits global integrity verification. This is a single-operator sandbox.
        return JSONResponse(
            fw.store.receipt(), headers={"Content-Disposition": "attachment; filename=receipt.json"}
        )

    @app.get("/runs")
    def run_list(request: Request):
        reports = []
        if Path(runs).exists():
            for file in sorted(Path(runs).glob("*/results.json")):
                try:
                    reports.append(
                        {
                            "name": file.parent.name,
                            "report": json.loads(file.read_text(encoding="utf-8")),
                        }
                    )
                except (ValueError, OSError):
                    reports.append({"name": file.parent.name, "error": "Report could not be read"})
        return render(request, "runs.html", title="Evaluation runs", reports=reports)

    return app
