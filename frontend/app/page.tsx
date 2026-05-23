"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { GeoJSONSource, Map, StyleSpecification } from "maplibre-gl";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAP_STYLE_URL = process.env.NEXT_PUBLIC_MAP_STYLE_URL;
const DEFAULT_MAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    cartoLight: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://d.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: "carto-light",
      type: "raster",
      source: "cartoLight",
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

const layers = [
  { key: "road_cycling", label: "Road cycling", color: "#c84e3c" },
  { key: "mountain_biking", label: "Mountain biking", color: "#497b57" },
  { key: "gravel_biking", label: "Gravel biking", color: "#b28747" },
  { key: "running", label: "Running", color: "#2d79a5" },
  { key: "trail_running", label: "Trail running", color: "#8f68b5" },
  { key: "open_water_swimming", label: "Open-water swimming", color: "#e67e22" }
];

type FeatureCollection = GeoJSON.FeatureCollection;
type Photo = { id: number; image_url: string; caption?: string | null; longitude: number; latitude: number };
type ImportJob = {
  id: number;
  status: "pending" | "running" | "completed" | "failed";
  activities_seen: number;
  activities_imported: number;
  activities_with_new_coverage: number;
  error?: string | null;
};
type StravaStatus = {
  connected: boolean;
  athlete_name?: string | null;
  athlete_id?: number | null;
};
type MapStats = {
  total_unique_distance_meters: number;
};

async function fetchJson<T>(path: string, fallback: T, options?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_URL}${path}`, { credentials: "include", ...options });
    return response.ok ? await response.json() : fallback;
  } catch {
    return fallback;
  }
}

export default function Home() {
  const mapNode = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const markerRefs = useRef<maplibregl.Marker[]>([]);
  const [coverage, setCoverage] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [visibleLayers, setVisibleLayers] = useState<Record<string, boolean>>(
    Object.fromEntries(layers.map((layer) => [layer.key, true]))
  );
  const [photosVisible, setPhotosVisible] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importJob, setImportJob] = useState<ImportJob | null>(null);
  const [stravaStatus, setStravaStatus] = useState<StravaStatus | null>(null);
  const [mapStats, setMapStats] = useState<MapStats | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<{ longitude: number; latitude: number } | null>(null);
  const [caption, setCaption] = useState("");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [connectingStrava, setConnectingStrava] = useState(false);
  const [connectNotice, setConnectNotice] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  useEffect(() => {
    async function loadAtlas() {
      const backendReachable = await fetch(`${API_URL}/health`, { credentials: "include" })
        .then((response) => response.ok)
        .catch(() => false);
      setApiError(backendReachable ? null : "Atlas backend is not reachable. Make sure the local backend is running on port 8000.");

      const [coveragePayload, photoPayload, latestJob, statusPayload, statsPayload] = await Promise.all([
        fetchJson<FeatureCollection>("/map/coverage", { type: "FeatureCollection", features: [] }),
        fetchJson<Photo[]>("/photos", []),
        fetchJson<ImportJob | null>("/sync/strava/latest", null),
        fetchJson<StravaStatus>("/auth/strava/status", { connected: false }),
        fetchJson<MapStats>("/map/stats", { total_unique_distance_meters: 0 }),
      ]);
      setCoverage(coveragePayload);
      setPhotos(photoPayload);
      if (latestJob) {
        setImportJob(latestJob);
        setImporting(latestJob.status === "pending" || latestJob.status === "running");
      }
      setStravaStatus(statusPayload);
      setMapStats(statsPayload);
    }

    loadAtlas().catch(() => {
      setApiError("Atlas backend is not reachable. Make sure the local backend is running on port 8000.");
      setStravaStatus({ connected: false });
      setMapStats({ total_unique_distance_meters: 0 });
    });
  }, []);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapNode.current,
      style: MAP_STYLE_URL ?? DEFAULT_MAP_STYLE,
      center: [-119.5, 39.5],
      zoom: 4,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    map.on("click", (event) => {
      setSelectedPoint({ longitude: event.lngLat.lng, latitude: event.lngLat.lat });
    });
    map.on("load", () => {
      map.addSource("coverage", { type: "geojson", data: coverage });
      for (const layer of layers) {
        map.addLayer({
          id: layer.key,
          type: "line",
          source: "coverage",
          filter: ["==", ["get", "atlas_type"], layer.key],
          paint: {
            "line-color": layer.color,
            "line-width": 2.5,
            "line-opacity": 0.95,
          },
        });
      }
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [coverage]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    const source = map.getSource("coverage") as GeoJSONSource | undefined;
    source?.setData(coverage);
  }, [coverage]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    for (const layer of layers) {
      if (map.getLayer(layer.key)) {
        map.setLayoutProperty(layer.key, "visibility", visibleLayers[layer.key] ? "visible" : "none");
      }
    }
  }, [visibleLayers]);

  const totalUniqueMiles = ((mapStats?.total_unique_distance_meters ?? 0) / 1609.344).toFixed(1);
  async function connectStrava() {
    if (connectingStrava) return;
    setConnectingStrava(true);
    setConnectError(null);
    setConnectNotice("Contacting the local Atlas backend…");

    const controller = new AbortController();
    const slowTimer = window.setTimeout(() => {
      setConnectNotice("Still working — check that the local backend is running on port 8000.");
    }, 8000);
    const timeoutTimer = window.setTimeout(() => controller.abort(), 75000);

    try {
      const response = await fetch(`${API_URL}/auth/strava/connect`, {
        method: "POST",
        credentials: "include",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Atlas returned ${response.status}`);
      }
      const payload = await response.json();
      if (!payload.url) {
        throw new Error("Atlas did not return a Strava authorization URL");
      }
      setConnectNotice("Opening Strava authorization…");
      window.location.assign(payload.url);
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === "AbortError";
      setConnectError(
        aborted
          ? "Strava connection timed out. Check that the local backend is running, then try again."
          : error instanceof Error
            ? error.message
            : "Unable to start Strava connection."
      );
      setConnectNotice(null);
      setConnectingStrava(false);
    } finally {
      window.clearTimeout(slowTimer);
      window.clearTimeout(timeoutTimer);
    }
  }

  async function syncStrava() {
    setImporting(true);
    setApiError(null);
    try {
      const response = await fetch(`${API_URL}/sync/strava`, { method: "POST", credentials: "include" });
      const job = await response.json();
      setImportJob(job);
      if (!response.ok) {
        setImporting(false);
      }
    } catch {
      setImporting(false);
      setApiError("Atlas backend is not reachable. Make sure the local backend is running on port 8000.");
    }
  }

  useEffect(() => {
    if (!importing || !importJob) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/sync/strava/latest`, { credentials: "include" });
        if (!response.ok) return;
        const job = await response.json();
        setImportJob(job);
        if (job.status === "completed" || job.status === "failed") {
          setImporting(false);
          setCoverage(await fetchJson<FeatureCollection>("/map/coverage", { type: "FeatureCollection", features: [] }));
          setMapStats(await fetchJson<MapStats>("/map/stats", { total_unique_distance_meters: 0 }));
        }
      } catch {
        setImporting(false);
        setApiError("Atlas backend is not reachable. Make sure the local backend is running on port 8000.");
      }
    }, 2000);
    return () => window.clearInterval(timer);
  }, [importing, importJob?.id]);

  async function uploadPhoto() {
    if (!selectedPoint || !photoFile) return;
    setUploading(true);
    const form = new FormData();
    form.append("longitude", String(selectedPoint.longitude));
    form.append("latitude", String(selectedPoint.latitude));
    form.append("caption", caption);
    form.append("file", photoFile);
    const response = await fetch(`${API_URL}/photos`, {
      method: "POST",
      body: form,
      credentials: "include",
    });
    if (response.ok) {
      const photo = await response.json();
      setPhotos((current) => [...current, photo]);
      setCaption("");
      setPhotoFile(null);
      setSelectedPoint(null);
    }
    setUploading(false);
  }

  useEffect(() => {
    if (!mapRef.current) return;
    markerRefs.current.forEach((marker) => marker.remove());
    markerRefs.current = [];
    if (!photosVisible) return;

    for (const photo of photos) {
      const element = document.createElement("button");
      element.className = "photo-pin";
      element.title = photo.caption ?? "Training memory";
      const image = document.createElement("img");
      image.src = photo.image_url;
      image.alt = photo.caption ?? "Training memory";
      element.appendChild(image);
      markerRefs.current.push(
        new maplibregl.Marker({ element }).setLngLat([photo.longitude, photo.latitude]).addTo(mapRef.current)
      );
    }
  }, [photos, photosVisible]);

  return (
    <main className="atlas-shell">
      <aside className="sidebar">
        <div className="brand">Atlas</div>
        <section>
          <h2>Strava</h2>
          <div className="connection-status">
            <strong>{stravaStatus?.connected ? "Connected" : "Not connected"}</strong>
            {stravaStatus?.athlete_name && <span>{stravaStatus.athlete_name}</span>}
          </div>
        </section>
        <section>
          <h2>Activities</h2>
          {layers.map((layer) => (
            <label key={layer.key} className="toggle-row">
              <span style={{ color: layer.color }}>●</span>
              <span>{layer.label}</span>
              <input
                type="checkbox"
                checked={visibleLayers[layer.key]}
                onChange={() => setVisibleLayers((current) => ({ ...current, [layer.key]: !current[layer.key] }))}
              />
            </label>
          ))}
        </section>
        <section>
          <h2>Photos</h2>
          <label className="toggle-row">
            <span>◉</span>
            <span>Photos</span>
            <input type="checkbox" checked={photosVisible} onChange={() => setPhotosVisible((value) => !value)} />
          </label>
        </section>
        <section>
          <h2>Add memory</h2>
          <div className="memory-form">
            <p>{selectedPoint ? "Location selected" : "Click the map to choose a location."}</p>
            <input
              type="file"
              accept="image/*"
              onChange={(event) => setPhotoFile(event.target.files?.[0] ?? null)}
            />
            <input
              type="text"
              placeholder="Caption"
              value={caption}
              onChange={(event) => setCaption(event.target.value)}
            />
            <button disabled={!selectedPoint || !photoFile || uploading} onClick={uploadPhoto}>
              {uploading ? "Uploading…" : "Add photo"}
            </button>
          </div>
        </section>
        <dl className="stats">
          <div>
            <dt>Unique terrain</dt>
            <dd>{totalUniqueMiles} mi</dd>
          </div>
          <div>
            <dt>Photos</dt>
            <dd>{photos.length}</dd>
          </div>
          {importJob && (
            <div>
              <dt>Sync</dt>
              <dd className="import-status">
                {importJob.status === "failed"
                  ? importJob.error ?? "Failed"
                  : `${importJob.activities_imported} new / ${importJob.activities_seen || "…"} checked`}
              </dd>
            </div>
          )}
        </dl>
      </aside>

      <section className="map-wrap">
        <header className="toolbar">
          <button onClick={syncStrava} disabled={importing || !stravaStatus?.connected}>
            {importing ? "Syncing…" : "Sync Strava"}
          </button>
          {apiError && <p className="connect-feedback error" role="status">{apiError}</p>}
          <div className="connect-action">
            <button className="primary" onClick={connectStrava} disabled={connectingStrava}>
              {connectingStrava ? "Connecting…" : stravaStatus?.connected ? "Reconnect Strava" : "Connect Strava"}
            </button>
            {(connectNotice || connectError) && (
              <p className={connectError ? "connect-feedback error" : "connect-feedback"} role="status" aria-live="polite">
                {connectError ?? connectNotice}
              </p>
            )}
          </div>
        </header>
        <div ref={mapNode} className="map" />
      </section>
    </main>
  );
}
