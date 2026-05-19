"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { GeoJSONSource, Map } from "maplibre-gl";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAP_STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_URL ?? "https://tiles.openfreemap.org/styles/positron";

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

  useEffect(() => {
    fetch(`${API_URL}/map/coverage`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : { type: "FeatureCollection", features: [] }))
      .then(setCoverage);
    fetch(`${API_URL}/photos`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : []))
      .then(setPhotos);
    fetch(`${API_URL}/imports/strava/history/latest`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((job) => {
        if (job) {
          setImportJob(job);
          setImporting(job.status === "pending" || job.status === "running");
        }
      });
    fetch(`${API_URL}/auth/strava/status`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : { connected: false }))
      .then(setStravaStatus);
    fetch(`${API_URL}/map/stats`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : { total_unique_distance_meters: 0 }))
      .then(setMapStats);
  }, []);

  useEffect(() => {
    if (!mapNode.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapNode.current,
      style: MAP_STYLE_URL,
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
    setConnectNotice("Contacting Strava… Render may need a moment to wake up.");

    const controller = new AbortController();
    const slowTimer = window.setTimeout(() => {
      setConnectNotice("Still working — the free backend is probably waking up.");
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
          ? "Strava connection timed out while the backend was waking. Please try again."
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

  async function importHistory() {
    setImporting(true);
    const response = await fetch(`${API_URL}/imports/strava/history`, { method: "POST", credentials: "include" });
    const job = await response.json();
    setImportJob(job);
  }

  useEffect(() => {
    if (!importing || !importJob) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`${API_URL}/imports/strava/history/latest`, { credentials: "include" });
      if (!response.ok) return;
      const job = await response.json();
      setImportJob(job);
      if (job.status === "completed" || job.status === "failed") {
        setImporting(false);
        const coverageResponse = await fetch(`${API_URL}/map/coverage`, { credentials: "include" });
        setCoverage(await coverageResponse.json());
        const statsResponse = await fetch(`${API_URL}/map/stats`, { credentials: "include" });
        setMapStats(await statsResponse.json());
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
              <dt>Import</dt>
              <dd className="import-status">
                {importJob.status === "failed"
                  ? importJob.error ?? "Failed"
                  : `${importJob.activities_imported}/${importJob.activities_seen || "…"} activities`}
              </dd>
            </div>
          )}
        </dl>
      </aside>

      <section className="map-wrap">
        <header className="toolbar">
          <button onClick={importHistory} disabled={importing}>
            {importing ? "Importing…" : "Import history"}
          </button>
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
