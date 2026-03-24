import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


EVENT_COLUMNS = (
    "id",
    "type",
    "app",
    "module",
    "message",
    "DES.src",
    "DES.dst",
    "TOPO.src",
    "TOPO.dst",
    "module.src",
    "service",
    "time_in",
    "time_out",
    "time_emit",
    "time_reception",
)

LINK_COLUMNS = (
    "id",
    "type",
    "src",
    "dst",
    "app",
    "latency",
    "message",
    "ctime",
    "size",
    "buffer",
)


def _normalized_mapping(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key.strip() if isinstance(key, str) else key: value
        for key, value in data.items()
    }


def _normalize_groupby(groupby: Any) -> List[str]:
    if isinstance(groupby, str):
        return [groupby]
    return list(groupby)


def _quantile(name: str, value: float):
    def _inner(series: pd.Series) -> float:
        return float(series.quantile(value))

    _inner.__name__ = name
    return _inner


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if np.isnan(numeric) or np.isinf(numeric):
        return default
    return float(numeric)


def _canonical_edge(src: Any, dst: Any) -> Tuple[Any, Any]:
    return tuple(sorted((src, dst), key=lambda value: str(value)))


def _observation_window_from_frames(
    event_df: pd.DataFrame,
    link_df: pd.DataFrame,
) -> float:
    starts: List[float] = []
    ends: List[float] = []

    if not event_df.empty:
        for column in ("time_emit", "time_reception", "time_in"):
            if column not in event_df.columns:
                continue
            series = pd.to_numeric(event_df[column], errors="coerce").dropna()
            if not series.empty:
                starts.append(float(series.min()))
        if "time_out" in event_df.columns:
            series = pd.to_numeric(event_df["time_out"], errors="coerce").dropna()
            if not series.empty:
                ends.append(float(series.max()))

    if not link_df.empty:
        ctime = pd.to_numeric(link_df["ctime"], errors="coerce").dropna()
        latency = pd.to_numeric(link_df["latency"], errors="coerce").fillna(0.0)
        if not ctime.empty:
            starts.append(float(ctime.min()))
            ends.append(float((ctime + latency).max()))

    if not starts or not ends:
        return 0.0

    return max(float(max(ends) - min(starts)), 0.0)


class Metrics:
    """
    CSV writer used by :class:`yafs.core.Sim`.

    The class keeps the public contract historically used by ``core.py``:
    ``insert`` records event-level rows and ``insert_link`` records hop-level
    rows. The CSV schema is unchanged so older analysis scripts remain valid.
    """

    # Time-related metric identifiers
    TIME_LATENCY = "time_latency"
    TIME_WAIT = "time_wait"
    TIME_RESPONSE = "time_response"
    TIME_SERVICE = "time_service"
    TIME_TOTAL_RESPONSE = "time_total_response"

    # Energy-related metric identifiers
    WATT_SERVICE = "byService"
    WATT_UPTIME = "byUptime"

    EVENT_COLUMNS = EVENT_COLUMNS
    LINK_COLUMNS = LINK_COLUMNS

    def __init__(self, default_results_path: Optional[str] = None) -> None:
        path = default_results_path or "result"

        self.__filef = open(f"{path}.csv", "w", newline="")
        self.__filel = open(f"{path}_link.csv", "w", newline="")

        self.__ff = csv.writer(self.__filef)
        self.__ff_link = csv.writer(self.__filel)

        self.__ff.writerow(self.EVENT_COLUMNS)
        self.__ff_link.writerow(self.LINK_COLUMNS)

    def flush(self) -> None:
        self.__filef.flush()
        self.__filel.flush()

    def insert(self, value: Dict[str, Any]) -> None:
        self.__ff.writerow(
            [
                value["id"],
                value["type"],
                value["app"],
                value["module"],
                value["message"],
                value["DES.src"],
                value["DES.dst"],
                value["TOPO.src"],
                value["TOPO.dst"],
                value["module.src"],
                value["service"],
                value["time_in"],
                value["time_out"],
                value["time_emit"],
                value["time_reception"],
            ]
        )

    def insert_link(self, value: Dict[str, Any]) -> None:
        self.__ff_link.writerow(
            [
                value["id"],
                value["type"],
                value["src"],
                value["dst"],
                value["app"],
                value["latency"],
                value["message"],
                value["ctime"],
                value["size"],
                value["buffer"],
            ]
        )

    def close(self) -> None:
        self.__filef.close()
        self.__filel.close()


@dataclass(frozen=True)
class ServicePath:
    app_name: str
    path_id: int
    messages: Tuple[str, ...]

    @property
    def terminal_message(self) -> Optional[str]:
        return self.messages[-1] if self.messages else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_name": self.app_name,
            "path_id": self.path_id,
            "messages": list(self.messages),
            "terminal_message": self.terminal_message,
        }


@dataclass
class ServiceDefinition:
    name: str
    app_id: Optional[Any] = None
    deadline: Optional[float] = None
    has_backward_return: bool = False
    messages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    transmissions: List[Dict[str, Any]] = field(default_factory=list)
    paths: Tuple[ServicePath, ...] = field(default_factory=tuple)
    return_messages: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ServiceDefinition":
        raw = _normalized_mapping(data)

        name = str(raw.get("name"))
        app_id = raw.get("id")
        deadline = raw.get("deadline")

        transmissions = [
            _normalized_mapping(item)
            for item in raw.get("transmission", [])
            if isinstance(item, Mapping)
        ]
        messages = {
            str(msg["name"]): _normalized_mapping(msg)
            for msg in raw.get("message", [])
            if isinstance(msg, Mapping) and "name" in msg
        }

        return_messages = tuple(
            sorted(
                message_name
                for message_name, definition in messages.items()
                if str(definition.get("d")) == "None"
            )
        )
        has_backward_return = bool(raw.get("has_backward_return", False))
        if return_messages:
            has_backward_return = True

        produced_messages = {
            str(item["message_out"])
            for item in transmissions
            if item.get("message_out")
        }
        roots = [
            message_name
            for message_name, definition in messages.items()
            if str(definition.get("s")) == "None"
        ]
        if not roots:
            roots = sorted(
                {
                    str(item["message_in"])
                    for item in transmissions
                    if item.get("message_in")
                }
                - produced_messages
            )

        adjacency: Dict[str, List[str]] = {}
        for item in transmissions:
            message_in = item.get("message_in")
            message_out = item.get("message_out")
            if message_in and message_out:
                adjacency.setdefault(str(message_in), []).append(str(message_out))

        enumerated_paths: List[Tuple[str, ...]] = []

        def walk(message_name: str, current_path: List[str]) -> None:
            children = adjacency.get(message_name, [])
            if not children:
                enumerated_paths.append(tuple(current_path))
                return

            for child in children:
                if child in current_path:
                    continue
                walk(child, current_path + [child])

        for root in roots:
            walk(str(root), [str(root)])

        if not enumerated_paths:
            for root in roots:
                enumerated_paths.append((str(root),))

        paths = tuple(
            ServicePath(app_name=name, path_id=index, messages=path)
            for index, path in enumerate(enumerated_paths)
        )

        return cls(
            name=name,
            app_id=app_id,
            deadline=deadline,
            has_backward_return=has_backward_return,
            messages=messages,
            transmissions=transmissions,
            paths=paths,
            return_messages=return_messages,
        )

    def iter_paths(
        self,
        include_return_messages: bool = True,
    ) -> Iterable[ServicePath]:
        seen: set[Tuple[str, ...]] = set()

        for path in self.paths:
            messages = path.messages
            if not include_return_messages and self.return_messages:
                messages = tuple(
                    message
                    for message in messages
                    if message not in set(self.return_messages)
                )
            if not messages or messages in seen:
                continue
            seen.add(messages)
            yield ServicePath(
                app_name=self.name,
                path_id=path.path_id,
                messages=messages,
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "id": self.app_id,
            "deadline": self.deadline,
            "has_backward_return": self.has_backward_return,
            "messages": self.messages,
            "transmissions": self.transmissions,
            "paths": [path.to_dict() for path in self.paths],
            "return_messages": list(self.return_messages),
        }


def load_service_definitions(
    source: Optional[Any],
) -> Dict[str, ServiceDefinition]:
    """
    Load service definitions from a JSON path, a raw JSON object, or a list
    of already parsed dictionaries.
    """

    if source is None:
        return {}

    if isinstance(source, Path):
        raw_data = json.loads(source.read_text())
    elif isinstance(source, str):
        path = Path(source)
        raw_data = json.loads(path.read_text()) if path.exists() else json.loads(source)
    else:
        raw_data = source

    if isinstance(raw_data, ServiceDefinition):
        return {str(raw_data.name): raw_data}

    if isinstance(raw_data, Mapping) and "name" in raw_data:
        items = [raw_data]
    elif isinstance(raw_data, Mapping):
        definitions: Dict[str, ServiceDefinition] = {}
        for key, value in raw_data.items():
            if isinstance(value, ServiceDefinition):
                definitions[str(key)] = value
            elif isinstance(value, Mapping):
                definition = ServiceDefinition.from_dict(value)
                definitions[str(definition.name)] = definition
        return definitions
    else:
        items = list(raw_data)

    definitions = {}
    for item in items:
        if isinstance(item, ServiceDefinition):
            definition = item
        else:
            definition = ServiceDefinition.from_dict(item)
        definitions[str(definition.name)] = definition
    return definitions


def load_node_regions(source: Any) -> Dict[str, str]:
    """
    Load node -> region mappings from a dictionary or a topology JSON file.
    """

    if source is None:
        return {}

    if isinstance(source, Path):
        raw_data = json.loads(source.read_text())
    elif isinstance(source, str):
        path = Path(source)
        raw_data = json.loads(path.read_text()) if path.exists() else json.loads(source)
    else:
        raw_data = source

    if isinstance(raw_data, Mapping) and "clusters" not in raw_data:
        return {str(key): str(value) for key, value in raw_data.items()}

    regions: Dict[str, str] = {}
    for cluster in raw_data.get("clusters", []):
        # Prefer explicit cluster_region when present, since some lab
        # scenarios may store the "region" metadata there.
        region = cluster.get("cluster_region", cluster.get("region"))
        for node in cluster.get("nodes", []):
            node_name = node.get("name")
            if node_name and region:
                regions[str(node_name)] = str(region)
    return regions


class MetricsAnalyzer:
    """
    Rich metrics reader and analyser for the CSV files generated by YAFS.

    Parameters
    ----------
    defaultPath:
        Base path for ``<defaultPath>.csv`` and ``<defaultPath>_link.csv``.
    app_definition:
        Optional app/service definition source. It can be a file path, a JSON
        object, or a list of dictionaries with the same structure as
        ``appDefinition.json``.
    event_df / link_df:
        Optional preloaded dataframes, mainly useful for testing.
    """

    EVENT_COLUMNS = EVENT_COLUMNS
    LINK_COLUMNS = LINK_COLUMNS
    AUXILIARY_EVENT_TYPES = {"SRC_M", "LOST_M"}

    def __init__(
        self,
        defaultPath: str = "result",
        app_definition: Optional[Any] = None,
        event_df: Optional[pd.DataFrame] = None,
        link_df: Optional[pd.DataFrame] = None,
    ) -> None:
        base_path = Path(defaultPath)
        if base_path.suffix == ".csv":
            base_path = base_path.with_suffix("")

        if event_df is None:
            event_df = self._read_metrics_csv(
                base_path.with_suffix(".csv"),
                self.EVENT_COLUMNS,
            )
        if link_df is None:
            link_df = self._read_metrics_csv(
                base_path.parent / f"{base_path.name}_link.csv",
                self.LINK_COLUMNS,
            )

        self.default_path = str(base_path)
        self.df = self._prepare_events(event_df)
        self.df_link = self._prepare_links(link_df)
        self.service_definitions = load_service_definitions(app_definition)
        self._service_aliases = self._build_service_aliases(self.service_definitions)
        self._message_instances_cache: Optional[pd.DataFrame] = None

    @staticmethod
    def _read_metrics_csv(path: Path, expected_columns: Sequence[str]) -> pd.DataFrame:
        raw = pd.read_csv(path)
        normalized_columns = [str(column).strip() for column in raw.columns]

        if normalized_columns == list(expected_columns):
            raw.columns = list(expected_columns)
            return raw

        if set(normalized_columns) == set(expected_columns):
            renamed = raw.rename(columns=dict(zip(raw.columns, normalized_columns)))
            return renamed[list(expected_columns)]

        return pd.read_csv(path, names=list(expected_columns), header=None)

    @staticmethod
    def _prepare_events(df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()

        for column in ("id", "service", "time_in", "time_out", "time_emit", "time_reception"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

        sort_columns = [
            column
            for column in ("app", "id", "time_emit", "time_in", "message")
            if column in frame.columns
        ]
        if sort_columns and not frame.empty:
            frame = frame.sort_values(sort_columns).reset_index(drop=True)

        if "time_latency" not in frame.columns:
            frame["time_latency"] = frame["time_reception"] - frame["time_emit"]
        if "time_wait" not in frame.columns:
            frame["time_wait"] = frame["time_in"] - frame["time_reception"]
        if "time_service" not in frame.columns:
            frame["time_service"] = frame["time_out"] - frame["time_in"]
        if "time_response" not in frame.columns:
            frame["time_response"] = frame["time_out"] - frame["time_reception"]
        if "time_total_response" not in frame.columns:
            frame["time_total_response"] = frame["time_out"] - frame["time_emit"]

        return frame

    @staticmethod
    def _prepare_links(df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()

        for column in ("id", "latency", "ctime", "size", "buffer"):
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

        frame["arrival_time"] = frame["ctime"] + frame["latency"]

        sort_columns = [
            column
            for column in ("app", "id", "ctime", "message")
            if column in frame.columns
        ]
        if sort_columns and not frame.empty:
            frame = frame.sort_values(sort_columns).reset_index(drop=True)

        return frame

    @staticmethod
    def _build_service_aliases(
        definitions: Mapping[str, ServiceDefinition],
    ) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for name, definition in definitions.items():
            aliases[str(name)] = str(name)
            if definition.app_id is not None:
                aliases[str(definition.app_id)] = str(name)
        return aliases

    def _resolve_app_key(self, app_name: Any) -> str:
        return self._service_aliases.get(str(app_name), str(app_name))

    def _filter_by_app(
        self,
        frame: pd.DataFrame,
        app_name: Optional[Any] = None,
    ) -> pd.DataFrame:
        if app_name is None or "app" not in frame.columns:
            return frame
        app_key = self._resolve_app_key(app_name)
        return frame[frame["app"].map(str) == app_key].copy()

    @staticmethod
    def _filter_by_time_range(
        frame: pd.DataFrame,
        *,
        from_time: Optional[float] = None,
        to_time: Optional[float] = None,
        time_column: str = "end_time",
    ) -> pd.DataFrame:
        if frame.empty or time_column not in frame.columns:
            return frame.copy()

        filtered = frame.copy()
        series = pd.to_numeric(filtered[time_column], errors="coerce")
        mask = series.notna()
        if from_time is not None:
            mask &= series >= float(from_time)
        if to_time is not None:
            mask &= series <= float(to_time)
        return filtered[mask].copy()

    def compute_times_df(self) -> None:
        self.df = self._prepare_events(self.df)
        self._message_instances_cache = None

    def bytes_transmitted(self) -> float:
        return float(self.df_link["size"].sum())

    def count_messages(self) -> int:
        return int(len(self.df_link))

    def average_messages_not_transmitted(self) -> float:
        return float(np.mean(self.df_link["buffer"])) if not self.df_link.empty else 0.0

    def peak_messages_not_transmitted(self) -> float:
        return float(np.max(self.df_link["buffer"])) if not self.df_link.empty else 0.0

    def messages_not_transmitted(self) -> pd.Series:
        if self.df_link.empty:
            return pd.Series(dtype=float)
        return self.df_link["buffer"].iloc[-1:]

    def utilization(self, id_entity: Any, total_time: float, from_time: float = 0.0) -> float:
        if total_time <= from_time:
            return 0.0

        frame = self.df[self.df["time_out"] >= from_time]
        values = frame.groupby("DES.dst", dropna=False)["time_service"].sum()
        return float(values.get(id_entity, 0.0) / (total_time - from_time))

    def times(self, time: str, value: str = "mean") -> pd.DataFrame:
        if time in self.df.columns:
            return self.df.groupby("message", dropna=False).agg({time: value})

        instances = self.message_instances()
        if time in instances.columns:
            return instances.groupby("message", dropna=False).agg({time: value})

        raise KeyError(f"Unknown metric column: {time}")

    def average_loop_response(self, time_loops: Sequence[Sequence[str]]) -> List[float]:
        instances = self.message_instances()
        if instances.empty:
            return [0.0 for _ in time_loops]

        response = instances.groupby("message", dropna=False).agg(
            {"observed_response_time": ["mean", "count"]}
        )
        response.columns = ["_".join(column).strip() for column in response.columns.values]

        results = []
        for loop in time_loops:
            total = 0.0
            for message in loop:
                if message in response.index:
                    total += float(
                        response.loc[message, "observed_response_time_mean"]
                    )
            results.append(total)
        return results

    def observation_window(self) -> float:
        """
        Return the observed simulation window covered by the metrics traces.
        """
        return _observation_window_from_frames(self.df, self.df_link)

    def link_utilization(
        self,
        topology: Any,
        include_unused: bool = False,
    ) -> pd.DataFrame:
        """
        Compute utilization for each physical link in the topology.
        """
        duration = self.observation_window()
        rows: Dict[Tuple[Any, Any], Dict[str, Any]] = {}

        if not self.df_link.empty:
            frame = self.df_link.copy()
            frame["edge"] = frame.apply(
                lambda row: _canonical_edge(row["src"], row["dst"]),
                axis=1,
            )
            grouped = (
                frame.groupby("edge", dropna=False)
                .agg(
                    messages=("message", "count"),
                    requests=("id", "nunique"),
                    total_size=("size", "sum"),
                    latency_mean=("latency", "mean"),
                    buffer_mean=("buffer", "mean"),
                )
                .reset_index()
            )

            for row in grouped.itertuples(index=False):
                edge = row.edge
                bandwidth_available = _safe_float(
                    topology.get_edge(edge).get("BW"),
                    0.0,
                )
                bandwidth_used = (
                    _safe_float(row.total_size, 0.0) / duration if duration > 0 else 0.0
                )
                rows[edge] = {
                    "src": edge[0],
                    "dst": edge[1],
                    "messages": int(row.messages),
                    "requests": int(row.requests),
                    "total_size": _safe_float(row.total_size, 0.0),
                    "latency_mean": _safe_float(row.latency_mean, 0.0),
                    "buffer_mean": _safe_float(row.buffer_mean, 0.0),
                    "bandwidth_used": bandwidth_used,
                    "bandwidth_available": bandwidth_available,
                    "utilization": (
                        bandwidth_used / bandwidth_available
                        if bandwidth_available > 0.0
                        else 0.0
                    ),
                    "distance_km": _safe_float(
                        topology.get_edge_distance(edge),
                        0.0,
                    ),
                }

        if include_unused:
            for edge in topology.get_edges():
                canonical_edge = _canonical_edge(edge[0], edge[1])
                if canonical_edge in rows:
                    continue
                rows[canonical_edge] = {
                    "src": canonical_edge[0],
                    "dst": canonical_edge[1],
                    "messages": 0,
                    "requests": 0,
                    "total_size": 0.0,
                    "latency_mean": 0.0,
                    "buffer_mean": 0.0,
                    "bandwidth_used": 0.0,
                    "bandwidth_available": _safe_float(
                        topology.get_edge(edge).get("BW"),
                        0.0,
                    ),
                    "utilization": 0.0,
                    "distance_km": _safe_float(
                        topology.get_edge_distance(edge),
                        0.0,
                    ),
                }

        if not rows:
            return pd.DataFrame(
                columns=[
                    "src",
                    "dst",
                    "messages",
                    "requests",
                    "total_size",
                    "latency_mean",
                    "buffer_mean",
                    "bandwidth_used",
                    "bandwidth_available",
                    "utilization",
                    "distance_km",
                ]
            )

        return (
            pd.DataFrame.from_records(list(rows.values()))
            .sort_values(["src", "dst"])
            .reset_index(drop=True)
        )

    def request_hops(self, app_name: Optional[Any] = None) -> pd.DataFrame:
        """
        Return the number of hops traversed by each request.
        """
        frame = self._filter_by_app(self.df_link, app_name)
        if frame.empty:
            return pd.DataFrame(columns=["id", "app", "total_hops"])

        return (
            frame.groupby(["id", "app"], dropna=False)
            .agg(total_hops=("message", "count"))
            .reset_index()
            .sort_values(["app", "id"])
            .reset_index(drop=True)
        )

    def average_application_response_latency(
        self,
        app_name: Optional[Any] = None,
        strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> pd.DataFrame:
        """
        Return mean response latency per application.
        """
        summary = self.summarize_service_response(
            strategy=strategy,
            include_return_messages=include_return_messages,
        )
        summary = self._filter_by_app(summary, app_name)
        if summary.empty:
            return pd.DataFrame(columns=["app", "response_mean"])
        return summary[["app", "response_mean"]].reset_index(drop=True)

    def request_distance_breakdown(
        self,
        topology: Any,
        app_name: Optional[Any] = None,
    ) -> pd.DataFrame:
        """
        Return the total traversed distance per request in kilometres.
        """
        frame = self._filter_by_app(self.df_link, app_name)
        if frame.empty:
            return pd.DataFrame(columns=["id", "app", "distance_km"])

        working = frame.copy()
        working["distance_km"] = working.apply(
            lambda row: _safe_float(
                topology.get_edge_distance((row["src"], row["dst"])),
                0.0,
            ),
            axis=1,
        )
        return (
            working.groupby(["id", "app"], dropna=False)
            .agg(distance_km=("distance_km", "sum"))
            .reset_index()
            .sort_values(["app", "id"])
            .reset_index(drop=True)
        )

    def application_distance_breakdown(self, topology: Any) -> pd.DataFrame:
        """
        Aggregate request distance by application.
        """
        breakdown = self.request_distance_breakdown(topology)
        if breakdown.empty:
            return pd.DataFrame(
                columns=["app", "distance_mean_km", "distance_total_km"]
            )

        return (
            breakdown.groupby("app", dropna=False)
            .agg(
                distance_mean_km=("distance_km", "mean"),
                distance_total_km=("distance_km", "sum"),
            )
            .reset_index()
        )

    def mean_topology_congestion(self, topology: Any) -> float:
        utilization = self.link_utilization(topology, include_unused=True)
        if utilization.empty:
            return 0.0
        return _safe_float(utilization["utilization"].mean(), 0.0)

    def total_bandwidth_used(self, topology: Any) -> float:
        utilization = self.link_utilization(topology, include_unused=False)
        if utilization.empty:
            return 0.0
        return _safe_float(utilization["bandwidth_used"].sum(), 0.0)

    def total_bandwidth_available(self, topology: Any) -> float:
        if hasattr(topology, "total_bandwidth"):
            return _safe_float(topology.total_bandwidth(), 0.0)
        total = 0.0
        for edge in topology.get_edges():
            total += _safe_float(topology.get_edge(edge).get("BW"), 0.0)
        return total

    def total_links(self, topology: Any) -> int:
        if hasattr(topology, "total_links"):
            return int(topology.total_links())
        return int(len(list(topology.get_edges())))

    def _message_event_instances(self) -> pd.DataFrame:
        frame = self.df.copy()
        if "type" in frame.columns:
            frame = frame[~frame["type"].isin(self.AUXILIARY_EVENT_TYPES)].copy()

        if frame.empty:
            return pd.DataFrame(
                columns=[
                    "app",
                    "id",
                    "message",
                    "type",
                    "module",
                    "module.src",
                    "DES.src",
                    "DES.dst",
                    "TOPO.src",
                    "TOPO.dst",
                    "time_emit",
                    "time_reception",
                    "time_in",
                    "time_out",
                    "time_latency",
                    "time_wait",
                    "time_service",
                    "time_response",
                    "time_total_response",
                    "event_rows",
                ]
            )

        return (
            frame.groupby(["app", "id", "message"], dropna=False)
            .agg(
                {
                    "type": "last",
                    "module": "last",
                    "module.src": "last",
                    "DES.src": "last",
                    "DES.dst": "last",
                    "TOPO.src": "last",
                    "TOPO.dst": "last",
                    "time_emit": "min",
                    "time_reception": "max",
                    "time_in": "min",
                    "time_out": "max",
                    "time_latency": "sum",
                    "time_wait": "sum",
                    "time_service": "sum",
                    "time_response": "sum",
                    "time_total_response": "sum",
                }
            )
            .reset_index()
            .assign(event_rows=lambda frame: 1)
        )

    def emitted_request_breakdown(
        self,
        app_name: Optional[Any] = None,
        from_time: Optional[float] = None,
        to_time: Optional[float] = None,
        time_column: str = "time_emit",
    ) -> pd.DataFrame:
        frame = self.df.copy()
        if "type" in frame.columns:
            frame = frame[frame["type"] == "SRC_M"].copy()
        frame = self._filter_by_app(frame, app_name)
        frame = self._filter_by_time_range(
            frame,
            from_time=from_time,
            to_time=to_time,
            time_column=time_column,
        )
        if frame.empty:
            return pd.DataFrame(columns=["app", "requests_total"])

        return (
            frame.groupby("app", dropna=False)
            .agg(requests_total=("id", "nunique"))
            .reset_index()
        )

    def _message_link_instances(self) -> pd.DataFrame:
        if self.df_link.empty:
            return pd.DataFrame(
                columns=[
                    "app",
                    "id",
                    "message",
                    "network_nominal_time",
                    "first_hop_time",
                    "last_hop_time",
                    "link_arrival_time",
                    "actual_network_time",
                    "link_hops",
                    "payload_bytes",
                    "bytes_transmitted",
                    "buffer_mean",
                    "buffer_max",
                    "hop_path",
                    "link_rows",
                ]
            )

        summary = (
            self.df_link.groupby(["app", "id", "message"], dropna=False)
            .agg(
                {
                    "latency": "sum",
                    "ctime": ["min", "max"],
                    "arrival_time": "max",
                    "size": ["first", "sum"],
                    "buffer": ["mean", "max"],
                }
            )
            .reset_index()
        )
        summary.columns = [
            "app",
            "id",
            "message",
            "network_nominal_time",
            "first_hop_time",
            "last_hop_time",
            "link_arrival_time",
            "payload_bytes",
            "bytes_transmitted",
            "buffer_mean",
            "buffer_max",
        ]
        summary["actual_network_time"] = (
            summary["link_arrival_time"] - summary["first_hop_time"]
        )
        hop_counts = (
            self.df_link.groupby(["app", "id", "message"], dropna=False)
            .size()
            .reset_index(name="link_hops")
        )
        summary = summary.merge(hop_counts, on=["app", "id", "message"], how="left")
        summary["link_rows"] = summary["link_hops"]

        hop_paths = (
            self.df_link.groupby(["app", "id", "message"], dropna=False)[["src", "dst"]]
            .apply(
                lambda frame: tuple(
                    zip(frame["src"].tolist(), frame["dst"].tolist())
                )
            )
            .rename("hop_path")
            .reset_index()
        )

        return summary.merge(hop_paths, on=["app", "id", "message"], how="left")

    def message_instances(self) -> pd.DataFrame:
        """
        Return one row per ``(app, id, message)`` combining event and link data.
        """

        if self._message_instances_cache is not None:
            return self._message_instances_cache.copy()

        events = self._message_event_instances()
        links = self._message_link_instances()

        merged = events.merge(
            links,
            on=["app", "id", "message"],
            how="outer",
            suffixes=("", "_link"),
        )

        merged["stage_start_time"] = merged["time_emit"].combine_first(
            merged["first_hop_time"]
        )
        merged["stage_end_time"] = merged["time_out"].combine_first(
            merged["link_arrival_time"]
        )
        merged["observed_response_time"] = merged["time_total_response"].combine_first(
            merged["stage_end_time"] - merged["stage_start_time"]
        )
        merged["actual_network_time"] = merged["time_latency"].combine_first(
            merged["actual_network_time"]
        )
        merged["network_nominal_time"] = merged["network_nominal_time"].fillna(0.0)
        merged["link_hops"] = merged["link_hops"].fillna(0).astype(int)
        merged["event_rows"] = merged["event_rows"].fillna(0).astype(int)
        merged["link_rows"] = merged["link_rows"].fillna(0).astype(int)
        merged["is_link_only"] = merged["event_rows"].eq(0)
        merged["processing_time"] = merged["time_service"].fillna(0.0)
        merged["waiting_time"] = merged["time_wait"].fillna(0.0)
        merged["network_queue_time"] = (
            merged["actual_network_time"].fillna(0.0) - merged["network_nominal_time"]
        ).clip(lower=0.0)
        merged["payload_bytes"] = merged["payload_bytes"].where(
            merged["payload_bytes"].notna(),
            np.where(
                merged["link_hops"] > 0,
                merged["bytes_transmitted"] / merged["link_hops"],
                np.nan,
            ),
        )
        merged["completed"] = merged["stage_end_time"].notna()
        merged["app_key"] = merged["app"].map(str)

        sort_columns = [
            column
            for column in ("app", "id", "stage_start_time", "message")
            if column in merged.columns
        ]
        merged = merged.sort_values(sort_columns).reset_index(drop=True)
        self._message_instances_cache = merged
        return merged.copy()

    def message_breakdown(
        self,
        groupby: Any = ("app", "message"),
        app_name: Optional[Any] = None,
    ) -> pd.DataFrame:
        frame = self._filter_by_app(self.message_instances(), app_name)
        if frame.empty:
            return pd.DataFrame(columns=_normalize_groupby(groupby))

        group_columns = _normalize_groupby(groupby)
        return (
            frame.groupby(group_columns, dropna=False)
            .agg(
                requests=("id", "nunique"),
                completed=("completed", "sum"),
                observed_response_mean=("observed_response_time", "mean"),
                observed_response_p50=("observed_response_time", _quantile("p50", 0.50)),
                observed_response_p95=("observed_response_time", _quantile("p95", 0.95)),
                network_mean=("actual_network_time", "mean"),
                network_nominal_mean=("network_nominal_time", "mean"),
                network_queue_mean=("network_queue_time", "mean"),
                processing_mean=("processing_time", "mean"),
                waiting_mean=("waiting_time", "mean"),
                hops_mean=("link_hops", "mean"),
                payload_bytes_mean=("payload_bytes", "mean"),
            )
            .reset_index()
        )

    def link_breakdown(
        self,
        groupby: Any = ("src", "dst"),
        app_name: Optional[Any] = None,
    ) -> pd.DataFrame:
        frame = self._filter_by_app(self.df_link, app_name)
        if frame.empty:
            return pd.DataFrame(columns=_normalize_groupby(groupby))

        group_columns = _normalize_groupby(groupby)
        return (
            frame.groupby(group_columns, dropna=False)
            .agg(
                transmissions=("message", "size"),
                requests=("id", "nunique"),
                latency_mean=("latency", "mean"),
                latency_p95=("latency", _quantile("p95", 0.95)),
                size_mean=("size", "mean"),
                buffer_mean=("buffer", "mean"),
                buffer_max=("buffer", "max"),
            )
            .reset_index()
        )

    def request_breakdown(self, app_name: Optional[Any] = None) -> pd.DataFrame:
        frame = self._filter_by_app(self.message_instances(), app_name)
        if frame.empty:
            return pd.DataFrame(columns=["app", "id"])

        summary = (
            frame.groupby(["app", "id"], dropna=False)
            .agg(
                start_time=("stage_start_time", "min"),
                end_time=("stage_end_time", "max"),
                messages=("message", "size"),
                completed_messages=("completed", "sum"),
                total_observed_response=("observed_response_time", "sum"),
                total_network_time=("actual_network_time", "sum"),
                total_processing_time=("processing_time", "sum"),
                total_waiting_time=("waiting_time", "sum"),
                total_queue_time=("network_queue_time", "sum"),
                total_bytes=("bytes_transmitted", "sum"),
            )
            .reset_index()
        )
        summary["service_makespan"] = summary["end_time"] - summary["start_time"]
        return summary

    def get_service_definition(self, app_name: Any) -> Optional[ServiceDefinition]:
        return self.service_definitions.get(self._resolve_app_key(app_name))

    def service_paths(
        self,
        app_name: Optional[Any] = None,
        include_return_messages: bool = True,
    ) -> Dict[str, List[Tuple[str, ...]]]:
        if app_name is not None:
            definition = self.get_service_definition(app_name)
            if definition is None:
                return {}
            return {
                definition.name: [
                    tuple(path.messages)
                    for path in definition.iter_paths(
                        include_return_messages=include_return_messages
                    )
                ]
            }

        return {
            name: [
                tuple(path.messages)
                for path in definition.iter_paths(
                    include_return_messages=include_return_messages
                )
            ]
            for name, definition in self.service_definitions.items()
        }

    def service_path_breakdown(
        self,
        app_name: Optional[Any] = None,
        include_return_messages: bool = True,
    ) -> pd.DataFrame:
        instances = self.message_instances()
        if instances.empty or not self.service_definitions:
            return pd.DataFrame(
                columns=[
                    "app",
                    "id",
                    "path_id",
                    "messages",
                    "path_label",
                    "completed",
                    "missing_messages",
                    "expected_stages",
                    "observed_stages",
                    "start_time",
                    "end_time",
                    "path_response",
                    "partial_response",
                    "forward_response",
                    "return_response",
                    "network_time",
                    "network_nominal_time",
                    "network_queue_time",
                    "processing_time",
                    "waiting_time",
                ]
            )

        request_lookup = instances.set_index(["app_key", "id", "message"])
        records: List[Dict[str, Any]] = []

        if app_name is None:
            definitions = self.service_definitions.values()
        else:
            definition = self.get_service_definition(app_name)
            definitions = [] if definition is None else [definition]

        for definition in definitions:
            app_key = self._resolve_app_key(definition.name)
            request_ids = instances.loc[
                instances["app_key"] == app_key,
                "id",
            ].drop_duplicates()

            for request_id in request_ids:
                for path in definition.iter_paths(
                    include_return_messages=include_return_messages
                ):
                    stage_rows: List[pd.Series] = []
                    missing_messages: List[str] = []

                    for message_name in path.messages:
                        key = (app_key, request_id, message_name)
                        if key not in request_lookup.index:
                            missing_messages.append(message_name)
                            continue

                        row = request_lookup.loc[key]
                        if isinstance(row, pd.DataFrame):
                            row = row.iloc[0]
                        stage_rows.append(row)

                    observed_stages = len(stage_rows)
                    completed = observed_stages == len(path.messages) and bool(stage_rows)

                    start_time = np.nan
                    end_time = np.nan
                    partial_response = 0.0
                    forward_response = 0.0
                    return_response = 0.0
                    network_time = 0.0
                    network_nominal_time = 0.0
                    network_queue_time = 0.0
                    processing_time = 0.0
                    waiting_time = 0.0

                    if stage_rows:
                        start_time = _safe_float(stage_rows[0]["stage_start_time"], np.nan)
                        end_time = _safe_float(stage_rows[-1]["stage_end_time"], np.nan)

                        for message_name, row in zip(path.messages, stage_rows):
                            message_name = str(message_name)
                            observed = _safe_float(row["observed_response_time"], 0.0)
                            partial_response += observed
                            network_time += _safe_float(row["actual_network_time"], 0.0)
                            network_nominal_time += _safe_float(
                                row["network_nominal_time"],
                                0.0,
                            )
                            network_queue_time += _safe_float(
                                row["network_queue_time"],
                                0.0,
                            )
                            processing_time += _safe_float(row["processing_time"], 0.0)
                            waiting_time += _safe_float(row["waiting_time"], 0.0)

                            if message_name in definition.return_messages:
                                return_response += observed
                            else:
                                forward_response += observed

                    path_response = (
                        float(end_time - start_time)
                        if completed and not np.isnan(start_time) and not np.isnan(end_time)
                        else np.nan
                    )

                    records.append(
                        {
                            "app": definition.name,
                            "id": request_id,
                            "path_id": path.path_id,
                            "messages": path.messages,
                            "path_label": " -> ".join(path.messages),
                            "terminal_message": path.terminal_message,
                            "completed": completed,
                            "missing_messages": tuple(missing_messages),
                            "expected_stages": len(path.messages),
                            "observed_stages": observed_stages,
                            "start_time": start_time,
                            "end_time": end_time,
                            "path_response": path_response,
                            "partial_response": partial_response,
                            "forward_response": forward_response,
                            "return_response": return_response,
                            "network_time": network_time,
                            "network_nominal_time": network_nominal_time,
                            "network_queue_time": network_queue_time,
                            "processing_time": processing_time,
                            "waiting_time": waiting_time,
                        }
                    )

        frame = pd.DataFrame.from_records(records)
        if frame.empty:
            return frame
        return frame.sort_values(["app", "id", "path_id"]).reset_index(drop=True)

    def service_response(
        self,
        app_name: Optional[Any] = None,
        from_time: Optional[float] = None,
        to_time: Optional[float] = None,
        time_column: str = "end_time",
        strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> pd.DataFrame:
        paths = self.service_path_breakdown(
            app_name=app_name,
            include_return_messages=include_return_messages,
        )
        if paths.empty:
            return pd.DataFrame(columns=["app", "id", "service_response"])

        complete_paths = paths[paths["completed"]].copy()
        if complete_paths.empty:
            return pd.DataFrame(columns=["app", "id", "service_response"])

        strategy = strategy.lower()
        if strategy in {"critical_path", "critical", "max"}:
            selected = (
                complete_paths.sort_values(
                    ["app", "id", "path_response", "path_id"],
                    ascending=[True, True, False, True],
                )
                .groupby(["app", "id"], dropna=False)
                .head(1)
                .copy()
            )
        elif strategy in {"min", "fastest"}:
            selected = (
                complete_paths.sort_values(
                    ["app", "id", "path_response", "path_id"],
                    ascending=[True, True, True, True],
                )
                .groupby(["app", "id"], dropna=False)
                .head(1)
                .copy()
            )
        elif strategy in {"mean", "avg", "average"}:
            selected = (
                complete_paths.groupby(["app", "id"], dropna=False)
                .agg(
                    start_time=("start_time", "min"),
                    end_time=("end_time", "max"),
                    service_response=("path_response", "mean"),
                    forward_response=("forward_response", "mean"),
                    return_response=("return_response", "mean"),
                    network_time=("network_time", "mean"),
                    network_nominal_time=("network_nominal_time", "mean"),
                    network_queue_time=("network_queue_time", "mean"),
                    processing_time=("processing_time", "mean"),
                    waiting_time=("waiting_time", "mean"),
                    completed_paths=("path_id", "size"),
                )
                .reset_index()
            )
            return self._filter_by_time_range(
                selected,
                from_time=from_time,
                to_time=to_time,
                time_column=time_column,
            )
        elif strategy in {"sum", "aggregate"}:
            selected = (
                complete_paths.groupby(["app", "id"], dropna=False)
                .agg(
                    start_time=("start_time", "min"),
                    end_time=("end_time", "max"),
                    service_response=("path_response", "sum"),
                    forward_response=("forward_response", "sum"),
                    return_response=("return_response", "sum"),
                    network_time=("network_time", "sum"),
                    network_nominal_time=("network_nominal_time", "sum"),
                    network_queue_time=("network_queue_time", "sum"),
                    processing_time=("processing_time", "sum"),
                    waiting_time=("waiting_time", "sum"),
                    completed_paths=("path_id", "size"),
                )
                .reset_index()
            )
            return self._filter_by_time_range(
                selected,
                from_time=from_time,
                to_time=to_time,
                time_column=time_column,
            )
        else:
            raise ValueError(f"Unknown service response strategy: {strategy}")

        selected = selected.rename(columns={"path_response": "service_response"})

        counts = (
            paths.groupby(["app", "id"], dropna=False)
            .agg(
                defined_paths=("path_id", "size"),
                completed_paths=("completed", "sum"),
            )
            .reset_index()
        )
        selected = selected.merge(counts, on=["app", "id"], how="left")
        return self._filter_by_time_range(
            selected,
            from_time=from_time,
            to_time=to_time,
            time_column=time_column,
        )

    def summarize_service_response(
        self,
        app_name: Optional[Any] = None,
        from_time: Optional[float] = None,
        to_time: Optional[float] = None,
        time_column: str = "end_time",
        strategy: str = "critical_path",
        include_return_messages: bool = True,
    ) -> pd.DataFrame:
        paths = self.service_path_breakdown(
            app_name=app_name,
            include_return_messages=include_return_messages,
        )
        filtered_paths = self._filter_by_time_range(
            paths,
            from_time=from_time,
            to_time=to_time,
            time_column=time_column,
        )

        request_counts = pd.DataFrame(columns=["app"])
        successful_requests = pd.DataFrame(columns=["app", "requests_successful"])
        if not filtered_paths.empty:
            successful_requests = (
                filtered_paths.groupby(["app", "id"], dropna=False)
                .agg(completed_paths=("completed", "sum"))
                .reset_index()
            )
            successful_requests = successful_requests[
                successful_requests["completed_paths"] > 0
            ].copy()
            successful_requests = (
                successful_requests.groupby("app", dropna=False)
                .agg(requests_successful=("id", "nunique"))
                .reset_index()
            )

        emitted_requests = self.emitted_request_breakdown(
            app_name=app_name,
            from_time=from_time,
            to_time=to_time,
            time_column="time_emit",
        )
        if not emitted_requests.empty or not successful_requests.empty:
            request_counts = emitted_requests.merge(
                successful_requests,
                on="app",
                how="outer",
            )
            if "requests_total" not in request_counts.columns:
                request_counts["requests_total"] = 0
            if "requests_successful" not in request_counts.columns:
                request_counts["requests_successful"] = 0
            request_counts["requests_total"] = request_counts["requests_total"].fillna(0)
            request_counts["requests_successful"] = request_counts["requests_successful"].fillna(0)
            request_counts["requests_unsuccessful"] = (
                request_counts["requests_total"] - request_counts["requests_successful"]
            ).clip(lower=0)

        frame = self.service_response(
            app_name=app_name,
            from_time=from_time,
            to_time=to_time,
            time_column=time_column,
            strategy=strategy,
            include_return_messages=include_return_messages,
        )
        if frame.empty and request_counts.empty:
            return pd.DataFrame(columns=["app"])

        if frame.empty:
            summary = request_counts.copy()
            summary["response_mean"] = np.nan
            summary["response_p50"] = np.nan
            summary["response_p95"] = np.nan
            summary["response_max"] = np.nan
            summary["network_mean"] = np.nan
            summary["processing_mean"] = np.nan
            summary["waiting_mean"] = np.nan
            return summary

        summary = (
            frame.groupby("app", dropna=False)
            .agg(
                response_mean=("service_response", "mean"),
                response_p50=("service_response", _quantile("p50", 0.50)),
                response_p95=("service_response", _quantile("p95", 0.95)),
                response_max=("service_response", "max"),
                network_mean=("network_time", "mean"),
                processing_mean=("processing_time", "mean"),
                waiting_mean=("waiting_time", "mean"),
            )
            .reset_index()
        )
        if request_counts.empty:
            summary["requests_total"] = 0
            summary["requests_successful"] = 0
            summary["requests_unsuccessful"] = 0
            if not summary.empty:
                inferred = frame.groupby("app", dropna=False).agg(
                    requests_successful=("id", "nunique")
                ).reset_index()
                summary = summary.merge(inferred, on="app", how="left", suffixes=("", "_inferred"))
                summary["requests_successful"] = summary["requests_successful_inferred"].fillna(0)
                summary["requests_total"] = summary["requests_successful"]
                summary = summary.drop(columns=["requests_successful_inferred"])
            return summary

        summary = summary.merge(request_counts, on="app", how="outer")
        return summary

    def application_execution_cost_breakdown(self, topology: Any) -> pd.DataFrame:
        """
        Compute execution cost per application from service time and node COST.
        """
        if self.df.empty:
            return pd.DataFrame(
                columns=[
                    "app",
                    "TOPO.dst",
                    "model",
                    "type",
                    "service_time",
                    "cost",
                ]
            )

        node_info = topology.get_info()
        records: List[Dict[str, Any]] = []

        grouped = (
            self.df.groupby(["app", "TOPO.dst"], dropna=False)
            .agg(service_time=("time_service", "sum"))
            .reset_index()
        )

        for row in grouped.itertuples(index=False):
            node_id = getattr(row, "_1") if hasattr(row, "_1") else getattr(row, "TOPO_dst")
            info = node_info.get(node_id, {})
            cost_rate = _safe_float(info.get("COST"), 0.0)
            service_time = _safe_float(row.service_time, 0.0)
            records.append(
                {
                    "app": row.app,
                    "TOPO.dst": node_id,
                    "model": info.get("model"),
                    "type": info.get("type"),
                    "service_time": service_time,
                    "cost": service_time * cost_rate,
                }
            )

        return pd.DataFrame.from_records(records)

    def application_cost_breakdown(self, topology: Any) -> pd.DataFrame:
        """
        Backwards-compatible alias for execution-based cost breakdown.
        """
        return self.application_execution_cost_breakdown(topology)

    def summarize_application_execution_cost(self, topology: Any) -> pd.DataFrame:
        breakdown = self.application_execution_cost_breakdown(topology)
        if breakdown.empty:
            return pd.DataFrame(columns=["app", "execution_cost", "service_time"])

        return (
            breakdown.groupby("app", dropna=False)
            .agg(
                execution_cost=("cost", "sum"),
                service_time=("service_time", "sum"),
            )
            .reset_index()
        )

    def summarize_application_cost(self, topology: Any) -> pd.DataFrame:
        """
        Backwards-compatible alias for execution-based application cost.
        """
        return self.summarize_application_execution_cost(topology)

    def summarize_application_execution_metrics(
        self,
        topology: Any,
        strategy: str = "critical_path",
        include_return_messages: bool = True,
        node_regions: Optional[Any] = None,
        egress_cost_per_gb: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Build one summary row per application combining response and cost.
        """
        response = self.summarize_service_response(
            strategy=strategy,
            include_return_messages=include_return_messages,
        )
        cost = self.summarize_application_execution_cost(topology)

        if response.empty and cost.empty:
            return pd.DataFrame(
                columns=[
                    "app",
                    "requests",
                    "response_mean",
                    "response_p50",
                    "response_p95",
                    "response_max",
                    "network_mean",
                    "processing_mean",
                    "waiting_mean",
                    "execution_cost",
                    "service_time",
                    "egress_cost",
                    "total_cost",
                ]
            )

        summary = response.merge(cost, on="app", how="outer")

        if node_regions is not None and egress_cost_per_gb is not None:
            egress = self.estimate_egress_cost(
                node_regions=node_regions,
                cost_per_gb=float(egress_cost_per_gb),
                by_request=False,
            )
            if not egress.empty:
                egress = (
                    egress.groupby("app", dropna=False)
                    .agg(egress_cost=("egress_cost", "sum"))
                    .reset_index()
                )
                summary = summary.merge(egress, on="app", how="left")

        if "egress_cost" not in summary.columns:
            summary["egress_cost"] = 0.0

        for column in (
            "requests",
            "response_mean",
            "response_p50",
            "response_p95",
            "response_max",
            "network_mean",
            "processing_mean",
            "waiting_mean",
            "execution_cost",
            "service_time",
            "egress_cost",
        ):
            if column in summary.columns:
                summary[column] = summary[column].fillna(0.0)

        summary["total_cost"] = summary["execution_cost"] + summary["egress_cost"]
        return summary.sort_values("app").reset_index(drop=True)

    def summarize_application_metrics(
        self,
        topology: Any,
        strategy: str = "critical_path",
        include_return_messages: bool = True,
        node_regions: Optional[Any] = None,
        egress_cost_per_gb: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Backwards-compatible alias for execution-based application metrics.
        """
        return self.summarize_application_execution_metrics(
            topology=topology,
            strategy=strategy,
            include_return_messages=include_return_messages,
            node_regions=node_regions,
            egress_cost_per_gb=egress_cost_per_gb,
        )

    def estimate_egress_cost(
        self,
        node_regions: Any,
        cost_per_gb: float,
        app_name: Optional[Any] = None,
        by_request: bool = False,
        from_time: Optional[float] = None,
        to_time: Optional[float] = None,
        time_column: str = "stage_end_time",
    ) -> pd.DataFrame:
        """
        Estimate inter-region egress cost.

        Notes
        -----
        This requires extra region metadata. ``node_regions`` can be a
        ``{node_name: region}`` mapping or a topology JSON file with
        ``clusters[].region`` and ``clusters[].nodes[].name``.
        """

        regions = load_node_regions(node_regions)
        frame = self._filter_by_app(self.message_instances(), app_name)
        frame = self._filter_by_time_range(
            frame,
            from_time=from_time,
            to_time=to_time,
            time_column=time_column,
        )
        if frame.empty:
            return pd.DataFrame(columns=["app", "id", "egress_cost"])

        enriched = frame.copy()
        enriched["src_region"] = enriched["TOPO.src"].map(regions)
        enriched["dst_region"] = enriched["TOPO.dst"].map(regions)
        enriched = enriched[
            enriched["src_region"].notna()
            & enriched["dst_region"].notna()
            & (enriched["src_region"] != enriched["dst_region"])
        ].copy()

        if enriched.empty:
            return pd.DataFrame(columns=["app", "id", "egress_cost"])

        enriched["egress_cost"] = (
            enriched["payload_bytes"].fillna(0.0) / 1e9
        ) * float(cost_per_gb)

        group_columns = ["app", "id"] if by_request else ["app", "message"]
        return (
            enriched.groupby(group_columns, dropna=False)
            .agg(
                egress_cost=("egress_cost", "sum"),
                payload_bytes=("payload_bytes", "sum"),
                crossings=("message", "size"),
            )
            .reset_index()
        )

    def get_watt(self, totaltime: float, topology: Any, by: str = Metrics.WATT_SERVICE):
        results: Dict[Any, Dict[str, Any]] = {}
        node_info = topology.get_info()

        if by == Metrics.WATT_SERVICE:
            nodes = self.df.groupby("TOPO.dst", dropna=False).agg({"time_service": "sum"})
            for node_id in nodes.index:
                info = node_info[node_id]
                results[node_id] = {
                    "model": info.get("model"),
                    "type": info.get("type"),
                    "watt": nodes.loc[node_id].time_service * info.get("WATT", 0.0),
                }
        else:
            for node_key, info in node_info.items():
                uptime = info.get("uptime", (0, None))
                start = uptime[0] if len(uptime) > 0 else 0
                end = uptime[1] if len(uptime) > 1 and uptime[1] else totaltime
                active_time = end - start
                results[node_key] = {
                    "model": info.get("model"),
                    "type": info.get("type"),
                    "watt": active_time * info.get("WATT", 0.0),
                    "uptime": active_time,
                }

        return results

    def get_cost_cloud(self, topology: Any):
        total_cost = 0.0
        results: Dict[Any, Dict[str, Any]] = {}
        node_info = topology.get_info()
        nodes = self.df.groupby("TOPO.dst", dropna=False).agg({"time_service": "sum"})

        for node_id in nodes.index:
            info = node_info[node_id]
            node_cost = nodes.loc[node_id].time_service * info.get("COST", 0.0)
            if node_cost <= 0:
                continue
            results[node_id] = {
                "model": info.get("model"),
                "type": info.get("type"),
                "cost": node_cost,
            }
            total_cost += node_cost

        return float(total_cost), results

    def showLoops(self, time_loops: Sequence[Sequence[str]]) -> List[float]:
        results = self.average_loop_response(time_loops)
        for index, loop in enumerate(time_loops):
            print("\t\t%i - %s :\t %f" % (index, str(loop), results[index]))
        return results

    def showResults(
        self,
        total_time: float,
        topology: Any,
        time_loops: Optional[Sequence[Sequence[str]]] = None,
    ) -> None:
        print("\tSimulation Time: %0.2f" % total_time)

        if time_loops is not None:
            print("\tApplication loops delays:")
            results = self.average_loop_response(time_loops)
            for index, loop in enumerate(time_loops):
                print("\t\t%i - %s :\t %f" % (index, str(loop), results[index]))

        print("\tEnergy Consumed (WATTS by UpTime):")
        values = self.get_watt(total_time, topology, Metrics.WATT_UPTIME)
        for node in values:
            print("\t\t%s - %s :\t %.2f" % (node, values[node]["model"], values[node]["watt"]))

        print("\tEnergy Consumed by Service (WATTS by Service Time):")
        values = self.get_watt(total_time, topology, Metrics.WATT_SERVICE)
        for node in values:
            print("\t\t%s - %s :\t %.2f" % (node, values[node]["model"], values[node]["watt"]))

        print("\tCost of execution in cloud:")
        total, _ = self.get_cost_cloud(topology)
        print("\t\t%.8f" % total)

        print("\tNetwork bytes transmitted:")
        print("\t\t%.1f" % self.bytes_transmitted())

    def showResults2(
        self,
        total_time: float,
        time_loops: Optional[Sequence[Sequence[str]]] = None,
    ) -> None:
        print("\tSimulation Time: %0.2f" % total_time)

        if time_loops is not None:
            print("\tApplication loops delays:")
            results = self.average_loop_response(time_loops)
            for index, loop in enumerate(time_loops):
                print("\t\t%i - %s :\t %f" % (index, str(loop), results[index]))

        print("\tNetwork bytes transmitted:")
        print("\t\t%.1f" % self.bytes_transmitted())

    def valueLoop(
        self,
        total_time: float,
        time_loops: Optional[Sequence[Sequence[str]]] = None,
    ) -> Optional[float]:
        del total_time
        if time_loops is not None:
            results = self.average_loop_response(time_loops)
            for index, _ in enumerate(time_loops):
                return results[index]
        return None

    def get_df_modules(self) -> pd.DataFrame:
        grouped = self.df.groupby(["module", "DES.dst"], dropna=False).agg(
            {"service": ["mean", "sum", "count"]}
        )
        return grouped.reset_index()

    def get_df_service_utilization(self, service: str, time: float) -> pd.DataFrame:
        grouped = self.df.groupby(["module", "DES.dst"], dropna=False).agg(
            {"service": ["mean", "sum", "count"]}
        )
        grouped.reset_index(inplace=True)
        result = pd.DataFrame()
        result["module"] = grouped[grouped.module == service].module
        result["utilization"] = grouped[grouped.module == service]["service"]["sum"] * 100 / time
        return result
