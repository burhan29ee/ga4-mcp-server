#!/usr/bin/env python3
"""
ga4-mcp-server — a Google Analytics 4 MCP server with read AND write access.

Authentication is via a Google Cloud service account. Set the environment
variable GOOGLE_APPLICATION_CREDENTIALS to the path of the service-account JSON
key file. The service account must be granted access on the target GA4
account or property (Viewer/Analyst for reads, Editor for writes) from the
Google Analytics admin UI.

Reads use the Analytics Data API (reports, realtime) and the Analytics Admin
API (property configuration). Writes use the Analytics Admin API (custom
dimensions & metrics, key events, audiences, Measurement Protocol secrets) and
the Measurement Protocol collect endpoint (sending events).
"""

import os
import json
import urllib.request
import urllib.error
from typing import Optional

from google.oauth2 import service_account

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
    RunRealtimeReportRequest,
)

from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
from google.analytics.admin_v1beta.types import (
    CustomDimension,
    CustomMetric,
    KeyEvent,
    MeasurementProtocolSecret,
)

# Audiences live in the v1alpha surface.
from google.analytics.admin_v1alpha import (
    AnalyticsAdminServiceClient as AlphaAdminClient,
)
from google.analytics.admin_v1alpha.types import (
    Audience,
    AudienceFilterClause,
    AudienceSimpleFilter,
    AudienceFilterExpression,
    AudienceFilterExpressionList,
    AudienceEventFilter,
    AudienceFilterScope,
)

from mcp.server.fastmcp import FastMCP

# analytics.edit is a superset that also permits reads; readonly included for safety.
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/analytics.edit",
]

mcp = FastMCP("ga4")

# --- lazy, cached client construction (so importing the module needs no creds) --
_clients: dict = {}


def _credentials():
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path:
        raise RuntimeError(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. Point it at the "
            "service-account JSON key file."
        )
    if not os.path.exists(key_path):
        raise RuntimeError(f"Service-account key file not found: {key_path}")
    return service_account.Credentials.from_service_account_file(key_path, scopes=SCOPES)


def data_client() -> BetaAnalyticsDataClient:
    if "data" not in _clients:
        _clients["data"] = BetaAnalyticsDataClient(credentials=_credentials())
    return _clients["data"]


def admin_client() -> AnalyticsAdminServiceClient:
    if "admin" not in _clients:
        _clients["admin"] = AnalyticsAdminServiceClient(credentials=_credentials())
    return _clients["admin"]


def admin_alpha_client() -> AlphaAdminClient:
    if "admin_alpha" not in _clients:
        _clients["admin_alpha"] = AlphaAdminClient(credentials=_credentials())
    return _clients["admin_alpha"]


def _prop(property_id: str) -> str:
    """Normalize a property id to 'properties/NNN'."""
    pid = str(property_id).strip()
    if pid.startswith("properties/"):
        return pid
    pid = pid.lstrip("pP")
    return f"properties/{pid}"


# ---------------------------------------------------------------------------
# Discovery / read: account & property structure
# ---------------------------------------------------------------------------

@mcp.tool()
def list_account_summaries() -> list[dict]:
    """List every GA4 account and its properties the service account can see.
    Returns account name/id plus each property's display name and numeric id.
    Call this first to discover property ids for the other tools."""
    out = []
    for s in admin_client().list_account_summaries():
        out.append(
            {
                "account": s.account,
                "account_display_name": s.display_name,
                "properties": [
                    {
                        "property": p.property,
                        "property_id": p.property.split("/")[-1],
                        "display_name": p.display_name,
                    }
                    for p in s.property_summaries
                ],
            }
        )
    return out


@mcp.tool()
def get_property_details(property_id: str) -> dict:
    """Get configuration details for one GA4 property (name, time zone,
    currency, industry, create time)."""
    p = admin_client().get_property(name=_prop(property_id))
    return {
        "name": p.name,
        "display_name": p.display_name,
        "time_zone": p.time_zone,
        "currency_code": p.currency_code,
        "industry_category": p.industry_category.name,
        "create_time": p.create_time.isoformat() if p.create_time else None,
    }


@mcp.tool()
def list_data_streams(property_id: str) -> list[dict]:
    """List the data streams (web/app) on a GA4 property. The stream id (last
    path segment of 'name') is needed by the Measurement Protocol secret tools."""
    out = []
    for s in admin_client().list_data_streams(parent=_prop(property_id)):
        out.append(
            {
                "name": s.name,
                "stream_id": s.name.split("/")[-1],
                "display_name": s.display_name,
                "type": s.type_.name,
                "measurement_id": getattr(getattr(s, "web_stream_data", None), "measurement_id", None),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Reporting: Data API
# ---------------------------------------------------------------------------

@mcp.tool()
def run_report(
    property_id: str,
    metrics: list[str],
    dimensions: Optional[list[str]] = None,
    start_date: str = "28daysAgo",
    end_date: str = "today",
    limit: int = 100,
) -> dict:
    """Run a GA4 report. metrics/dimensions are GA4 API names (e.g. metrics
    ['activeUsers','conversions'], dimensions ['date','sessionDefaultChannelGroup']).
    Dates accept YYYY-MM-DD or relative forms like '28daysAgo' / 'today'."""
    req = RunReportRequest(
        property=_prop(property_id),
        metrics=[Metric(name=m) for m in metrics],
        dimensions=[Dimension(name=d) for d in (dimensions or [])],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=limit,
    )
    resp = data_client().run_report(req)
    dim_headers = [h.name for h in resp.dimension_headers]
    met_headers = [h.name for h in resp.metric_headers]
    rows = [
        {
            **{dim_headers[i]: v.value for i, v in enumerate(r.dimension_values)},
            **{met_headers[i]: v.value for i, v in enumerate(r.metric_values)},
        }
        for r in resp.rows
    ]
    return {
        "dimension_headers": dim_headers,
        "metric_headers": met_headers,
        "row_count": resp.row_count,
        "rows": rows,
    }


@mcp.tool()
def run_realtime_report(
    property_id: str,
    metrics: list[str],
    dimensions: Optional[list[str]] = None,
    limit: int = 100,
) -> dict:
    """Run a GA4 realtime report (last ~30 minutes). Example: metrics
    ['activeUsers'], dimensions ['country','unifiedScreenName']."""
    req = RunRealtimeReportRequest(
        property=_prop(property_id),
        metrics=[Metric(name=m) for m in metrics],
        dimensions=[Dimension(name=d) for d in (dimensions or [])],
        limit=limit,
    )
    resp = data_client().run_realtime_report(req)
    dim_headers = [h.name for h in resp.dimension_headers]
    met_headers = [h.name for h in resp.metric_headers]
    rows = [
        {
            **{dim_headers[i]: v.value for i, v in enumerate(r.dimension_values)},
            **{met_headers[i]: v.value for i, v in enumerate(r.metric_values)},
        }
        for r in resp.rows
    ]
    return {"dimension_headers": dim_headers, "metric_headers": met_headers, "rows": rows}


# ---------------------------------------------------------------------------
# Custom dimensions (read + write)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_custom_dimensions(property_id: str) -> list[dict]:
    """List custom dimensions defined on a GA4 property."""
    return [
        {
            "name": d.name,
            "display_name": d.display_name,
            "parameter_name": d.parameter_name,
            "scope": d.scope.name,
            "description": d.description,
        }
        for d in admin_client().list_custom_dimensions(parent=_prop(property_id))
    ]


@mcp.tool()
def create_custom_dimension(
    property_id: str,
    parameter_name: str,
    display_name: str,
    scope: str = "EVENT",
    description: str = "",
) -> dict:
    """Create a custom dimension. parameter_name is the event parameter / user
    property key; scope is 'EVENT', 'USER' or 'ITEM'. display_name may contain
    only letters, numbers, underscores and spaces."""
    dim = CustomDimension(
        parameter_name=parameter_name,
        display_name=display_name,
        description=description,
        scope=CustomDimension.DimensionScope[scope.upper()],
    )
    created = admin_client().create_custom_dimension(parent=_prop(property_id), custom_dimension=dim)
    return {
        "name": created.name,
        "display_name": created.display_name,
        "parameter_name": created.parameter_name,
        "scope": created.scope.name,
    }


@mcp.tool()
def archive_custom_dimension(property_id: str, custom_dimension_id: str) -> dict:
    """Archive (delete) a custom dimension. custom_dimension_id may be the
    numeric id or the full 'properties/NNN/customDimensions/MMM' name."""
    cid = str(custom_dimension_id)
    name = cid if "/" in cid else f"{_prop(property_id)}/customDimensions/{cid}"
    admin_client().archive_custom_dimension(name=name)
    return {"archived": name}


# ---------------------------------------------------------------------------
# Custom metrics (read + write)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_custom_metrics(property_id: str) -> list[dict]:
    """List custom metrics defined on a GA4 property."""
    return [
        {
            "name": m.name,
            "display_name": m.display_name,
            "parameter_name": m.parameter_name,
            "measurement_unit": m.measurement_unit.name,
            "scope": m.scope.name,
            "description": m.description,
        }
        for m in admin_client().list_custom_metrics(parent=_prop(property_id))
    ]


@mcp.tool()
def create_custom_metric(
    property_id: str,
    parameter_name: str,
    display_name: str,
    measurement_unit: str = "STANDARD",
    scope: str = "EVENT",
    description: str = "",
) -> dict:
    """Create a custom metric. measurement_unit is one of STANDARD, CURRENCY,
    FEET, METERS, KILOMETERS, MILES, MILLISECONDS, SECONDS, MINUTES, HOURS."""
    met = CustomMetric(
        parameter_name=parameter_name,
        display_name=display_name,
        description=description,
        measurement_unit=CustomMetric.MeasurementUnit[measurement_unit.upper()],
        scope=CustomMetric.MetricScope[scope.upper()],
    )
    created = admin_client().create_custom_metric(parent=_prop(property_id), custom_metric=met)
    return {
        "name": created.name,
        "display_name": created.display_name,
        "parameter_name": created.parameter_name,
        "measurement_unit": created.measurement_unit.name,
    }


# ---------------------------------------------------------------------------
# Key events / conversions (read + write)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_key_events(property_id: str) -> list[dict]:
    """List key events (conversions) on a GA4 property."""
    return [
        {
            "name": k.name,
            "event_name": k.event_name,
            "counting_method": k.counting_method.name,
            "deletable": k.deletable,
            "custom": k.custom,
        }
        for k in admin_client().list_key_events(parent=_prop(property_id))
    ]


@mcp.tool()
def create_key_event(property_id: str, event_name: str, counting_method: str = "ONCE_PER_EVENT") -> dict:
    """Mark an event as a key event (conversion). counting_method is
    'ONCE_PER_EVENT' or 'ONCE_PER_SESSION'."""
    ke = KeyEvent(event_name=event_name, counting_method=KeyEvent.CountingMethod[counting_method.upper()])
    created = admin_client().create_key_event(parent=_prop(property_id), key_event=ke)
    return {
        "name": created.name,
        "event_name": created.event_name,
        "counting_method": created.counting_method.name,
    }


# ---------------------------------------------------------------------------
# Audiences (read + write)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_audiences(property_id: str) -> list[dict]:
    """List audiences defined on a GA4 property."""
    return [
        {
            "name": a.name,
            "display_name": a.display_name,
            "description": a.description,
            "membership_duration_days": a.membership_duration_days,
        }
        for a in admin_alpha_client().list_audiences(parent=_prop(property_id))
    ]


@mcp.tool()
def create_event_audience(
    property_id: str,
    display_name: str,
    event_name: str,
    membership_duration_days: int = 30,
    description: str = "",
) -> dict:
    """Create a GA4 audience of users who triggered a given event (e.g.
    'purchase', 'generate_lead') — useful for remarketing lists that can be
    shared to Google Ads. membership_duration_days is how long a user stays in
    the audience (max 540)."""
    # GA4 requires the top-level expression to be an and_group of or_groups.
    inner = AudienceFilterExpression(event_filter=AudienceEventFilter(event_name=event_name))
    or_expr = AudienceFilterExpression(or_group=AudienceFilterExpressionList(filter_expressions=[inner]))
    top = AudienceFilterExpression(and_group=AudienceFilterExpressionList(filter_expressions=[or_expr]))
    simple = AudienceSimpleFilter(
        scope=AudienceFilterScope.AUDIENCE_FILTER_SCOPE_ACROSS_ALL_SESSIONS,
        filter_expression=top,
    )
    clause = AudienceFilterClause(
        clause_type=AudienceFilterClause.AudienceClauseType.INCLUDE,
        simple_filter=simple,
    )
    aud = Audience(
        display_name=display_name,
        description=description,
        membership_duration_days=membership_duration_days,
        filter_clauses=[clause],
    )
    created = admin_alpha_client().create_audience(parent=_prop(property_id), audience=aud)
    return {
        "name": created.name,
        "display_name": created.display_name,
        "membership_duration_days": created.membership_duration_days,
    }


@mcp.tool()
def archive_audience(property_id: str, audience_id: str) -> dict:
    """Archive a GA4 audience. audience_id may be the numeric id or the full
    'properties/NNN/audiences/MMM' name."""
    aid = str(audience_id)
    name = aid if "/" in aid else f"{_prop(property_id)}/audiences/{aid}"
    admin_alpha_client().archive_audience(request={"name": name})
    return {"archived": name}


# ---------------------------------------------------------------------------
# Measurement Protocol: secrets (read + write) and sending events
# ---------------------------------------------------------------------------

@mcp.tool()
def list_measurement_protocol_secrets(property_id: str, stream_id: str) -> list[dict]:
    """List Measurement Protocol API secrets for a data stream. stream_id is
    the numeric id from list_data_streams."""
    parent = f"{_prop(property_id)}/dataStreams/{stream_id}"
    return [
        {"name": s.name, "display_name": s.display_name, "secret_value": s.secret_value}
        for s in admin_client().list_measurement_protocol_secrets(parent=parent)
    ]


@mcp.tool()
def create_measurement_protocol_secret(property_id: str, stream_id: str, display_name: str) -> dict:
    """Create a Measurement Protocol API secret on a data stream. Returns the
    secret_value (api_secret) needed by send_ga4_event. Treat it as sensitive."""
    parent = f"{_prop(property_id)}/dataStreams/{stream_id}"
    created = admin_client().create_measurement_protocol_secret(
        parent=parent, measurement_protocol_secret=MeasurementProtocolSecret(display_name=display_name)
    )
    return {"name": created.name, "display_name": created.display_name, "secret_value": created.secret_value}


@mcp.tool()
def delete_measurement_protocol_secret(property_id: str, stream_id: str, secret_id: str) -> dict:
    """Delete a Measurement Protocol API secret. secret_id may be the numeric
    id or the full resource name."""
    sid = str(secret_id)
    name = sid if "/" in sid else f"{_prop(property_id)}/dataStreams/{stream_id}/measurementProtocolSecrets/{sid}"
    admin_client().delete_measurement_protocol_secret(name=name)
    return {"deleted": name}


@mcp.tool()
def send_ga4_event(
    measurement_id: str,
    api_secret: str,
    client_id: str,
    event_name: str,
    params: Optional[dict] = None,
    validate: bool = False,
) -> dict:
    """Send an event into a GA4 property via the Measurement Protocol.
    measurement_id is the stream's 'G-XXXXXXX'; api_secret comes from a
    Measurement Protocol secret; client_id identifies the user/device. Set
    validate=True to hit GA4's debug/validation endpoint (checks the payload
    WITHOUT ingesting it) — recommended before real sends."""
    base = "https://www.google-analytics.com"
    path = "/debug/mp/collect" if validate else "/mp/collect"
    url = f"{base}{path}?measurement_id={measurement_id}&api_secret={api_secret}"
    body = json.dumps(
        {"client_id": client_id, "events": [{"name": event_name, "params": params or {}}]}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            text = resp.read().decode("utf-8") or ""
            result = {"status": resp.status, "endpoint": path}
            if text:
                try:
                    result["response"] = json.loads(text)
                except Exception:
                    result["response"] = text
            return result
    except urllib.error.HTTPError as e:
        return {"status": e.code, "endpoint": path, "error": e.read().decode("utf-8", "ignore")}


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
