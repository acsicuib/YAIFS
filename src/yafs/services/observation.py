"""Read-only placement observations built from configured state and traces.

Topology and deployments come from the live configuration. Request paths and
latency components come only from recorded events and link hops that share a
request id. A missing measurement stays unavailable; it is never filled in.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import pandas as pd

_AUXILIARY_EVENT_TYPES = {"SRC_M", "LOST_M"}
_TRACE_JOIN = "Events and link rows joined by application, request id, and message."


def observation_envelope(
    simulation_id: str,
    simulation_time: float,
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "simulation_id": simulation_id,
        "simulation_time": float(simulation_time),
        "data": data,
    }


def build_topology_view(
    *,
    directed: bool,
    nodes: list[dict[str, Any]],
    links: list[dict[str, Any]],
    cluster_id: str | None = None,
    node_id: str | None = None,
    include_resources: bool = True,
) -> dict[str, Any]:
    """Return clusters, nodes, and configured links.

    ``node_id`` selects that node, its adjacent nodes, and the links that
    touch it. ``cluster_id`` keeps nodes in the cluster and links with at
    least one end in the cluster, including the outside endpoint.
    """
    node_by_id = {str(item["id"]): item for item in nodes}
    if node_id is not None and str(node_id) not in node_by_id:
        raise ValueError(f"Node does not exist in the simulation: {node_id}")

    cluster_nodes = None
    if cluster_id is not None:
        cluster_nodes = {
            node_key
            for node_key, item in node_by_id.items()
            if str(item.get("cluster")) == str(cluster_id)
        }
        if not cluster_nodes:
            raise ValueError(f"Cluster does not exist in the simulation: {cluster_id}")
        if node_id is not None and str(node_id) not in cluster_nodes:
            raise ValueError(f"Node {node_id} is not in cluster {cluster_id}")

    if node_id is not None:
        focus = str(node_id)
        visible_links = [
            dict(link)
            for link in links
            if focus in {str(link["source_id"]), str(link["destination_id"])}
        ]
        selected = {focus}
        for link in visible_links:
            selected.add(str(link["source_id"]))
            selected.add(str(link["destination_id"]))
        scope = "node_neighborhood"
    elif cluster_nodes is not None:
        visible_links = [
            dict(link)
            for link in links
            if str(link["source_id"]) in cluster_nodes
            or str(link["destination_id"]) in cluster_nodes
        ]
        selected = set(cluster_nodes)
        for link in visible_links:
            selected.add(str(link["source_id"]))
            selected.add(str(link["destination_id"]))
        scope = "cluster"
    else:
        visible_links = [dict(link) for link in links]
        selected = set(node_by_id)
        scope = "full"

    visible_nodes = [
        node_by_id[node_key] for node_key in sorted(selected) if node_key in node_by_id
    ]

    clusters: dict[str, dict[str, Any]] = {}
    rendered_nodes = []
    for item in visible_nodes:
        cluster_name = item.get("cluster")
        if cluster_name is not None:
            entry = clusters.setdefault(
                str(cluster_name),
                {
                    "cluster_id": str(cluster_name),
                    "role": item.get("cluster_role"),
                    "region": item.get("cluster_region"),
                },
            )
            entry["role"] = entry["role"] or item.get("cluster_role")
            entry["region"] = entry["region"] or item.get("cluster_region")
        rendered = {
            "node_id": str(item["id"]),
            "cluster_id": None if cluster_name is None else str(cluster_name),
            "node_role": item.get("node_role"),
        }
        if include_resources:
            rendered["capacity"] = item.get("capacity")
            rendered["usage"] = item.get("usage")
        rendered_nodes.append(rendered)

    rendered_links = sorted(
        visible_links,
        key=lambda item: (str(item["source_id"]), str(item["destination_id"]), str(item.get("key") or "")),
    )
    for link in rendered_links:
        link.pop("key", None)

    return {
        "directed": bool(directed),
        "scope": scope,
        "units": {
            "delay": "simulation_time",
            "bandwidth": "configured_BW",
        },
        "clusters": [clusters[key] for key in sorted(clusters)],
        "nodes": rendered_nodes,
        "links": rendered_links,
    }


def build_deployments_view(
    *,
    definitions: list[dict[str, Any]],
    allocations: dict[str, dict[str, list[Any]]],
    alloc_des: dict[Any, Any],
    application_id: str | None = None,
    service_id: str | None = None,
) -> dict[str, Any]:
    """Return current replica placement, including services with no replica."""
    apps = []
    matched = False
    for definition in sorted(definitions, key=lambda item: str(item.get("name"))):
        app_name = str(definition.get("name"))
        app_key = definition.get("id", app_name)
        if application_id is not None and str(application_id) not in {app_name, str(app_key)}:
            continue
        matched = True
        modules = [
            module
            for module in definition.get("module", [])
            if isinstance(module, dict) and module.get("name") is not None
        ]
        module_names = {str(module["name"]) for module in modules}
        if service_id is not None and str(service_id) not in module_names:
            if application_id is not None:
                raise ValueError(
                    f"Service does not exist in application {app_name}: {service_id}"
                )
            continue
        placed = allocations.get(app_name, {})
        services = []
        for module in sorted(modules, key=lambda item: str(item.get("name"))):
            module_name = str(module["name"])
            if service_id is not None and module_name != str(service_id):
                continue
            replicas = []
            for des in placed.get(module_name, []):
                node_id = alloc_des.get(des)
                if node_id is None:
                    node_id = alloc_des.get(str(des))
                replicas.append(
                    {
                        "replica_id": _as_id(des),
                        "service_id": module_name,
                        "node_id": None if node_id is None else str(node_id),
                        "status": "deployed" if node_id is not None else "unplaced",
                    }
                )
            replicas.sort(key=lambda item: (str(item["node_id"]), str(item["replica_id"])))
            services.append(
                {
                    "service_id": module_name,
                    "status": "deployed" if replicas else "undeployed",
                    "replicas": replicas,
                }
            )
        apps.append(
            {
                "application_id": app_key if not isinstance(app_key, float) else app_name,
                "name": app_name,
                "chain": _service_chain(definition),
                "services": services,
            }
        )

    if application_id is not None and not matched:
        raise ValueError(f"Application does not exist in the simulation: {application_id}")
    if service_id is not None and not apps:
        raise ValueError(f"Service does not exist in the simulation: {service_id}")
    return {"applications": apps}


def build_request_paths(
    *,
    application_id: str,
    events: pd.DataFrame,
    links: pd.DataFrame,
    start_time: float | None = None,
    end_time: float | None = None,
    user_id: str | None = None,
    limit: int = 100,
    traces_available: bool = True,
) -> dict[str, Any]:
    """Group observed request routes. Link hops are recorded segments."""
    _validate_window(start_time, end_time, limit)
    requests = _observed_requests(events, links)
    selected, in_flight = _select_requests(
        requests,
        start_time=start_time,
        end_time=end_time,
        user_id=user_id,
    )
    groups = _group_requests(selected)
    groups.sort(key=lambda item: (-int(item["request_count"]), str(item["source_user_id"]), item["_signature"]))
    total = len(groups)
    truncated = total > limit
    visible = groups[:limit]
    for item in visible:
        item.pop("_signature", None)

    if not traces_available:
        availability = "unavailable"
        reason = "Trace files are not available for this simulation."
    elif not requests:
        availability = "empty"
        reason = "No requests have been recorded for this application."
    elif not selected:
        availability = "empty"
        reason = "No observed requests match the requested filters."
    elif any(item.get("missing_details") for item in visible) or any(
        item.get("missing_details") for item in groups
    ):
        availability = "partial"
        reason = (
            "Service hops are taken from event rows. Physical link sequences "
            "are included only where recorded hop rows form one chain."
        )
    else:
        availability = "complete"
        reason = None

    observed_times = [
        item.anchor
        for item in selected
        if item.anchor is not None
    ]
    return {
        "application_id": application_id,
        "window": _window(start_time, end_time, observed_times),
        "availability": availability,
        "reason": reason,
        "provenance": _TRACE_JOIN,
        "completed_requests_only": True,
        "in_flight_excluded": in_flight,
        "groups": visible,
        "group_count": total,
        "truncated": truncated,
        "limit": limit,
    }


def build_latency_breakdown(
    *,
    application_id: str,
    events: pd.DataFrame,
    links: pd.DataFrame,
    start_time: float | None = None,
    end_time: float | None = None,
    traces_available: bool = True,
) -> dict[str, Any]:
    """Separate measured latency pieces without forcing them to add up."""
    _validate_window(start_time, end_time, limit=1)
    requests = _observed_requests(events, links)
    selected, in_flight = _select_requests(
        requests,
        start_time=start_time,
        end_time=end_time,
        user_id=None,
    )
    observed_times = [item.anchor for item in selected if item.anchor is not None]
    window = _window(start_time, end_time, observed_times)

    if not traces_available:
        return _latency_payload(
            application_id,
            window,
            availability="unavailable",
            reason="Trace files are not available for this simulation.",
            sample_count=0,
            in_flight_excluded=in_flight,
            components=[],
            end_to_end=None,
        )
    if not selected:
        reason = (
            "No requests have been recorded for this application."
            if not requests
            else "No completed requests match the requested window."
        )
        return _latency_payload(
            application_id,
            window,
            availability="empty",
            reason=reason,
            sample_count=0,
            in_flight_excluded=in_flight,
            components=[],
            end_to_end=None,
        )

    end_to_end = _stats([item.end_to_end for item in selected if item.end_to_end is not None])
    catalog = [
        (
            "link_latency",
            "Recorded per-hop transmit plus propagation. The trace stores the sum, not the two parts.",
            [item.link_latency for item in selected if item.link_latency is not None],
        ),
        (
            "network_queue",
            "Hop-span minus recorded link latency, per message, then summed. Derived from timestamps.",
            [item.network_queue for item in selected if item.network_queue is not None],
        ),
        (
            "service_queue",
            "Recorded service wait: time_in minus time_reception, summed across stages.",
            [item.service_queue for item in selected if item.service_queue is not None],
        ),
        (
            "processing",
            "Recorded service time: time_out minus time_in, summed across stages.",
            [item.processing for item in selected if item.processing is not None],
        ),
    ]
    components = []
    unavailable = []
    for name, description, values in catalog:
        stats = _stats(values)
        if stats is None:
            unavailable.append({"component": name, "reason": "No recorded samples in the window."})
            continue
        components.append(
            {
                "component": name,
                "description": description,
                "additive": False,
                "statistics": stats,
            }
        )
    return _latency_payload(
        application_id,
        window,
        availability="complete" if components else "partial",
        reason=(
            "End-to-end time is the request wall clock. Components are recorded "
            "stage sums and are not required to add up to that wall clock."
        ),
        sample_count=len(selected),
        in_flight_excluded=in_flight,
        components=components,
        end_to_end=end_to_end,
        unavailable_components=unavailable,
    )


class _Request:
    def __init__(self) -> None:
        self.request_id = ""
        self.source_user_id: str | None = None
        self.emit_time: float | None = None
        self.completion_time: float | None = None
        self.anchor: float | None = None
        self.in_flight = False
        self.service_hops: list[dict[str, Any]] = []
        self.network_hops: list[dict[str, Any]] = []
        self.missing_details: list[str] = []
        self.end_to_end: float | None = None
        self.link_latency: float | None = None
        self.network_queue: float | None = None
        self.service_queue: float | None = None
        self.processing: float | None = None


def _observed_requests(events: pd.DataFrame, links: pd.DataFrame) -> list[_Request]:
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if events is not None and not events.empty:
        for record in events.to_dict(orient="records"):
            request_id = _as_id(record.get("id"))
            if request_id is None:
                continue
            by_id[request_id].append(record)

    links_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if links is not None and not links.empty:
        ordered = links.sort_values(
            [column for column in ("id", "message", "ctime") if column in links.columns]
        )
        for record in ordered.to_dict(orient="records"):
            request_id = _as_id(record.get("id"))
            if request_id is None:
                continue
            links_by_id[request_id].append(record)

    requests: list[_Request] = []
    for request_id in sorted(set(by_id) | set(links_by_id), key=str):
        item = _Request()
        item.request_id = request_id
        rows = by_id.get(request_id, [])
        sources = [row for row in rows if str(row.get("type")) == "SRC_M"]
        sources.sort(key=lambda row: _number(row.get("time_emit"), math.inf))
        if sources:
            item.source_user_id = _as_id(sources[0].get("DES.src"))
            item.emit_time = _optional_number(sources[0].get("time_emit"))
        service_rows = [
            row for row in rows if str(row.get("type")) not in _AUXILIARY_EVENT_TYPES
        ]
        service_rows.sort(
            key=lambda row: (
                _number(row.get("time_in"), math.inf),
                str(row.get("message")),
            )
        )
        if item.source_user_id is None and service_rows:
            item.source_user_id = _as_id(service_rows[0].get("DES.src"))
        if item.emit_time is None and rows:
            emits = [_optional_number(row.get("time_emit")) for row in rows]
            emits = [value for value in emits if value is not None]
            item.emit_time = min(emits) if emits else None

        completions = [
            _optional_number(row.get("time_out"))
            for row in service_rows
        ]
        completions = [value for value in completions if value is not None]
        item.completion_time = max(completions) if completions else None
        item.in_flight = bool(service_rows) and item.completion_time is None and not _lost(rows)
        item.anchor = item.completion_time if item.completion_time is not None else item.emit_time

        for row in service_rows:
            item.service_hops.append(
                {
                    "message": None if row.get("message") is None else str(row.get("message")),
                    "service_id": _as_id(row.get("module")),
                    "replica_id": _as_id(row.get("DES.dst")),
                    "node_id": _as_id(row.get("TOPO.dst")),
                }
            )

        waits = [_optional_number(row.get("time_wait")) for row in service_rows]
        services = [_optional_number(row.get("time_service")) for row in service_rows]
        if any(value is not None for value in waits):
            item.service_queue = sum(value or 0.0 for value in waits)
        if any(value is not None for value in services):
            item.processing = sum(value or 0.0 for value in services)
        if item.emit_time is not None and item.completion_time is not None:
            item.end_to_end = item.completion_time - item.emit_time

        hop_rows = links_by_id.get(request_id, [])
        message_order = [hop["message"] for hop in item.service_hops]
        hop_rows.sort(
            key=lambda row: (
                _message_rank(row.get("message"), message_order),
                _number(row.get("ctime"), math.inf),
            )
        )
        for row in hop_rows:
            source = _as_id(row.get("src"))
            destination = _as_id(row.get("dst"))
            if source is None or destination is None:
                continue
            item.network_hops.append(
                {
                    "source_id": source,
                    "destination_id": destination,
                    "latency": _optional_number(row.get("latency")),
                    "message": None if row.get("message") is None else str(row.get("message")),
                }
            )
        item.link_latency, item.network_queue = _link_components(hop_rows)
        if item.completion_time is None and hop_rows:
            arrivals = []
            for row in hop_rows:
                ctime = _optional_number(row.get("ctime"))
                latency = _optional_number(row.get("latency"))
                if ctime is None:
                    continue
                arrivals.append(ctime + (0.0 if latency is None else latency))
            if arrivals:
                item.completion_time = max(arrivals)
                item.anchor = item.completion_time
                if not item.service_hops:
                    item.missing_details.append("service_replica")
        if not item.network_hops or not _chains(item.network_hops):
            item.missing_details.append("physical_link_sequence")
        item.in_flight = item.completion_time is None and bool(rows or hop_rows)
        item.anchor = item.completion_time if item.completion_time is not None else item.emit_time
        requests.append(item)
    return requests


def _select_requests(
    requests: list[_Request],
    *,
    start_time: float | None,
    end_time: float | None,
    user_id: str | None,
) -> tuple[list[_Request], int]:
    selected: list[_Request] = []
    in_flight = 0
    for item in requests:
        if user_id is not None and item.source_user_id != str(user_id):
            continue
        if item.in_flight or item.completion_time is None:
            if item.in_flight or (item.service_hops and item.completion_time is None):
                in_flight += 1
            continue
        anchor = item.completion_time
        if start_time is not None and anchor < start_time:
            continue
        if end_time is not None and anchor > end_time:
            continue
        selected.append(item)
    return selected, in_flight


def _group_requests(requests: list[_Request]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[_Request]] = defaultdict(list)
    for item in requests:
        signature = (
            item.source_user_id,
            tuple(
                (hop["service_id"], hop["replica_id"], hop["node_id"])
                for hop in item.service_hops
            ),
            tuple(
                (hop["source_id"], hop["destination_id"])
                for hop in item.network_hops
            ),
        )
        grouped[signature].append(item)

    groups = []
    for signature, members in grouped.items():
        members.sort(key=lambda item: item.request_id)
        representative = members[0]
        latencies = [item.end_to_end for item in members if item.end_to_end is not None]
        groups.append(
            {
                "source_user_id": representative.source_user_id,
                "request_count": len(members),
                "request_ids": [item.request_id for item in members],
                "service_hops": representative.service_hops,
                "network_hops": [
                    {
                        "source_id": hop["source_id"],
                        "destination_id": hop["destination_id"],
                        "latency": hop["latency"],
                    }
                    for hop in representative.network_hops
                ],
                "missing_details": list(representative.missing_details),
                "latency": _stats(latencies),
                "_signature": str(signature),
            }
        )
    return groups


def _link_components(
    hop_rows: list[dict[str, Any]],
) -> tuple[float | None, float | None]:
    if not hop_rows:
        return None, None
    by_message: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in hop_rows:
        by_message[str(row.get("message"))].append(row)
    link_latency = 0.0
    network_queue = 0.0
    saw_latency = False
    for message in by_message:
        rows = sorted(by_message[message], key=lambda row: _number(row.get("ctime"), math.inf))
        latencies = [_optional_number(row.get("latency")) for row in rows]
        if any(value is not None for value in latencies):
            saw_latency = True
            link_latency += sum(value or 0.0 for value in latencies)
        ctimes = [_optional_number(row.get("ctime")) for row in rows]
        arrivals = []
        for row in rows:
            ctime = _optional_number(row.get("ctime"))
            latency = _optional_number(row.get("latency"))
            if ctime is None:
                continue
            arrivals.append(ctime if latency is None else ctime + latency)
        if ctimes and arrivals and any(value is not None for value in ctimes):
            span = max(arrivals) - min(value for value in ctimes if value is not None)
            nominal = sum(value or 0.0 for value in latencies)
            network_queue += max(span - nominal, 0.0)
    if not saw_latency:
        return None, None
    return link_latency, network_queue


def _chains(hops: list[dict[str, Any]]) -> bool:
    if not hops:
        return False
    for left, right in zip(hops, hops[1:]):
        if left["destination_id"] != right["source_id"]:
            return False
    return True


def _service_chain(definition: dict[str, Any]) -> list[str]:
    chain = definition.get("vnf_chain")
    if isinstance(chain, list) and chain:
        return [str(item) for item in chain]
    names: list[str] = []
    for message in definition.get("message", []):
        if not isinstance(message, dict):
            continue
        for key in ("s", "d"):
            value = message.get(key)
            if value is None or str(value) == "None" or str(value) in names:
                continue
            names.append(str(value))
    return names


def _window(
    start_time: float | None,
    end_time: float | None,
    observed: list[float],
) -> dict[str, Any]:
    start = start_time
    end = end_time
    if start is None and observed:
        start = min(observed)
    if end is None and observed:
        end = max(observed)
    return {
        "start": start,
        "end": end,
        "unit": "simulation_time",
        "bounds": "inclusive completion time",
    }


def _stats(values: list[float | None]) -> dict[str, Any] | None:
    numbers = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not numbers:
        return None
    series = pd.Series(numbers, dtype="float64")
    return {
        "mean": float(series.mean()),
        "p95": float(series.quantile(0.95)),
        "p99": float(series.quantile(0.99)),
        "sample_count": int(len(numbers)),
        "unit": "simulation_time",
    }


def _latency_payload(
    application_id: str,
    window: dict[str, Any],
    *,
    availability: str,
    reason: str | None,
    sample_count: int,
    in_flight_excluded: int,
    components: list[dict[str, Any]],
    end_to_end: dict[str, Any] | None,
    unavailable_components: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "application_id": application_id,
        "window": window,
        "availability": availability,
        "reason": reason,
        "provenance": _TRACE_JOIN,
        "sample_count": sample_count,
        "in_flight_excluded": in_flight_excluded,
        "additive": False,
        "end_to_end": end_to_end,
        "components": components,
        "unavailable_components": unavailable_components or [],
    }


def _validate_window(start_time: float | None, end_time: float | None, limit: int) -> None:
    if start_time is not None and end_time is not None and float(start_time) > float(end_time):
        raise ValueError("start_time must be less than or equal to end_time")
    if limit < 1:
        raise ValueError("limit must be at least 1")


def _as_id(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if text in {"", "nan", "None"}:
        return None
    return text


def _optional_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _number(value: Any, default: float) -> float:
    number = _optional_number(value)
    return default if number is None else number


def _message_rank(message: Any, order: list[str | None]) -> int:
    text = None if message is None else str(message)
    try:
        return order.index(text)
    except ValueError:
        return len(order)


def _lost(rows: list[dict[str, Any]]) -> bool:
    return any(str(row.get("type")) == "LOST_M" for row in rows)
