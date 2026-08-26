import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

type Violation = {
  buffer_m: number;
  intersects: boolean;
  num_intersections: number;
};

type Report = {
  violations: Violation[];
};

type Run = {
  id: string;
  report_url: string | null;
  report_pdf_url: string | null;
  evidence_url: string | null;
  map_url: string | null;
};

const defaultReport: Report = { violations: [] };

function App() {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const layerRef = useRef<L.GeoJSON | null>(null);
  const ndwiRef = useRef<L.ImageOverlay | null>(null);

  const [bbox, setBbox] = useState('77.55,12.85,77.57,12.87');
  const [point, setPoint] = useState('77.563,12.859');
  const [projectGeojson, setProjectGeojson] = useState<File | null>(null);
  const [ecPdf, setEcPdf] = useState<File | null>(null);
  const [enableNdwi, setEnableNdwi] = useState(false);
  const [status, setStatus] = useState('Idle. Upload a project or enter a point to start.');
  const [report, setReport] = useState<Report & { issues?: string[]; findings?: Array<{ buffer_m: number; risk: string; message: string }>; summary?: { status?: string; violations_found?: number; confidence?: string; tested_buffers_m?: number[] }; data_quality?: { water_source?: string; water_feature_count?: number } }>(defaultReport as any);
  const [links, setLinks] = useState<Record<string, string>>({});
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    mapInstance.current = L.map(mapRef.current, { zoomControl: true }).setView([20.2, 78.2], 5);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Tiles © Esri',
    }).addTo(mapInstance.current);
    L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19,
      attribution: 'Esri place labels',
      pane: 'overlayPane',
    }).addTo(mapInstance.current);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
      subdomains: 'abcd',
      attribution: '© OpenStreetMap contributors © CARTO',
      pane: 'overlayPane',
    }).addTo(mapInstance.current);

    return () => {
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, []);

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    try {
      const res = await fetch('/runs');
      const json = await res.json();
      setRuns(json.runs || []);
    } catch (err) {
      console.error('History load failed', err);
    }
  }

  function renderEvidence(data: any) {
    if (!mapInstance.current) return;
    if (layerRef.current) {
      mapInstance.current.removeLayer(layerRef.current);
      layerRef.current = null;
    }

    layerRef.current = L.geoJSON(data, {
      style: (feature: any) => {
        if (feature.properties?.type === 'project') {
          return { color: '#34d399', weight: 2, fillOpacity: 0.08 };
        }
        if (feature.properties?.type === 'buffer') {
          return { color: '#fbbf24', weight: 1, fillOpacity: 0.2 };
        }
        return { color: '#3b82f6', weight: 1.5, fillOpacity: 0.18 };
      },
      onEachFeature: (feature: any, layer: L.Layer) => {
        if (feature.properties) {
          const popupLayer = layer as L.Layer & { bindPopup: (content: string) => void };
          popupLayer.bindPopup(`<pre>${JSON.stringify(feature.properties, null, 2)}</pre>`);
        }
      },
    }).addTo(mapInstance.current);

    const bounds = layerRef.current.getBounds();
    if (bounds.isValid()) {
      mapInstance.current.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
    }
  }

  async function handleRun() {
    setLoading(true);
    setStatus('Sending detection request...');

    const form = new FormData();
    if (bbox.trim()) form.append('bbox', bbox.trim());
    if (point.trim()) form.append('project_point', point.trim());
    if (projectGeojson) form.append('project_geojson', projectGeojson);
    if (ecPdf) form.append('ec_pdf', ecPdf);
    form.append('enable_ndwi', enableNdwi ? '1' : '0');

    try {
      const res = await fetch('/detect', { method: 'POST', body: form });
      const json = await res.json();

      if (!res.ok) {
        throw new Error(json.error || 'Detection request failed');
      }

      const nextReport = json.report || defaultReport;
      setReport(nextReport);
      setLinks({
        report: json.report_url || '',
        reportPdf: json.report_pdf_url || '',
        evidence: json.evidence_url || '',
        map: json.map_url || '',
        ecParse: json.ec_parse_url || '',
        ndwi: json.ndwi_url || '',
      });
      const summary = nextReport.summary || {};
      const issues = nextReport.issues || [];
      if (issues.length > 0) {
        setStatus(`Analysis complete. ${summary.status === 'likely_violation' ? 'Likely violation found.' : 'No direct violation detected.'} ${issues[0]}`);
      } else {
        setStatus('Detection completed successfully.');
      }

      if (json.evidence_url) {
        const evidenceRes = await fetch(json.evidence_url);
        const evidenceJson = await evidenceRes.json();
        renderEvidence(evidenceJson);
      }

      if (json.ndwi_url && mapInstance.current) {
        if (ndwiRef.current) {
          mapInstance.current.removeLayer(ndwiRef.current);
        }
        ndwiRef.current = L.imageOverlay(json.ndwi_url, [[-90, -180], [90, 180]], { opacity: 0.6 });
        ndwiRef.current.addTo(mapInstance.current);
      }

      await loadRuns();
    } catch (err: any) {
      console.error(err);
      setStatus(err.message || 'Detection failed.');
    } finally {
      setLoading(false);
    }
  }

  const violationCount = report.violations.length;
  const highRiskCount = report.violations.filter((v) => v.intersects).length;
  const uniqueBuffers = new Set(report.violations.map((v) => v.buffer_m)).size;
  const findings = (report as any).findings || [];
  const issues = (report as any).issues || [];
  const summary = (report as any).summary || {};
  const waterSource = (report as any).data_quality?.water_source || 'unknown';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-badge">WB</div>
          <div>
            <h1>Waterbody Buffer<br />Detection</h1>
            <small>Fast compliance screening</small>
          </div>
        </div>

        <div className="panel card">
          <p className="eyebrow">Detection inputs</p>

          <label htmlFor="bbox">BBox (optional)</label>
          <input id="bbox" value={bbox} onChange={(e) => setBbox(e.target.value)} placeholder="77.55,12.85,77.57,12.87" />

          <label htmlFor="point">Project point (optional)</label>
          <input id="point" value={point} onChange={(e) => setPoint(e.target.value)} placeholder="77.563,12.859" />

          <label htmlFor="project-geojson">Project GeoJSON (optional)</label>
          <input id="project-geojson" type="file" accept=".geojson,application/geo+json,application/json" onChange={(e) => setProjectGeojson(e.target.files?.[0] || null)} />

          <label htmlFor="ec-pdf">EC PDF (optional)</label>
          <input id="ec-pdf" type="file" accept="application/pdf" onChange={(e) => setEcPdf(e.target.files?.[0] || null)} />

          <div className="checkbox-row">
            <input id="ndwi" type="checkbox" checked={enableNdwi} onChange={(e) => setEnableNdwi(e.target.checked)} />
            <label htmlFor="ndwi">Enable NDWI analysis</label>
          </div>

          <div className="button-row">
            <button className="primary" type="button" onClick={handleRun} disabled={loading}>
              {loading ? 'Running…' : 'Run detection'}
            </button>
            <button className="secondary" type="button" onClick={() => {
              setBbox('77.55,12.85,77.57,12.87');
              setPoint('77.563,12.859');
            }}>
              Load sample
            </button>
          </div>

          <div className="status-box">{status}</div>
        </div>

        <div className="panel card history">
          {issues.length > 0 && (
            <div className="analysis-box">
              <p className="eyebrow">Detailed findings</p>
              <ul>
                {issues.map((issue: string, idx: number) => <li key={idx}>{issue}</li>)}
              </ul>
            </div>
          )}

          {findings.length > 0 && (
            <div className="analysis-box compact">
              <p className="eyebrow">Risk notes</p>
              {findings.map((item: any, idx: number) => (
                <div className="finding-row" key={idx}>
                  <span className={`badge ${item.risk === 'high' ? 'danger' : 'ok'}`}>{item.risk}</span>
                  <span>{item.message}</span>
                </div>
              ))}
            </div>
          )}

          <div className="mini-meta">
            <small>Water source: {waterSource}</small>
            {summary.confidence && <small>Confidence: {summary.confidence}</small>}
          </div>

          <p className="eyebrow">Recent runs</p>
          <div className="history-list">
            {runs.length === 0 ? (
              <div className="history-item muted">No runs yet.</div>
            ) : (
              runs.slice(0, 6).map((run) => (
                <div className="history-item" key={run.id}>
                  <div>
                    <strong>{run.id}</strong>
                    <small>{run.report_url ? 'report available' : 'no report'}</small>
                  </div>
                  <button type="button" onClick={async () => {
                    if (run.evidence_url) {
                      const res = await fetch(run.evidence_url);
                      const json = await res.json();
                      renderEvidence(json);
                    }
                    if (run.map_url) {
                      const img = document.getElementById('preview') as HTMLImageElement;
                      if (img) {
                        img.src = run.map_url;
                        img.style.display = 'block';
                      }
                    }
                  }}>
                    Open
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <div className="topbar">
          <h2>Environmental clearance screening dashboard</h2>
          <span className="pill">Live analysis</span>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <span className="label">Violation checks</span>
            <span className="value">{violationCount}</span>
          </div>
          <div className="stat-card">
            <span className="label">High risk</span>
            <span className="value">{highRiskCount}</span>
          </div>
          <div className="stat-card">
            <span className="label">Buffer zones</span>
            <span className="value">{uniqueBuffers}</span>
          </div>
          <div className="stat-card">
            <span className="label">Last run</span>
            <span className="value">{new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        </div>

        <div className="content-grid">
          <section className="map-panel card">
            <div className="panel-header">
              <h3>Spatial evidence</h3>
              <span className="badge ok">Ready</span>
            </div>
            <div ref={mapRef} className="map-view" />
          </section>

          <aside className="results-panel card">
            <div className="panel-header">
              <h3>Detection results</h3>
            </div>
            <div className="result-body">
              <table>
                <thead>
                  <tr>
                    <th>Buffer</th>
                    <th>Intersects</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  {report.violations.length === 0 ? (
                    <tr>
                      <td colSpan={3}>No violations recorded.</td>
                    </tr>
                  ) : (
                    report.violations.map((item) => (
                      <tr key={item.buffer_m}>
                        <td>{Math.round(item.buffer_m)} m</td>
                        <td>
                          <span className={`badge ${item.intersects ? 'danger' : 'success'}`}>
                            {item.intersects ? 'Yes' : 'No'}
                          </span>
                        </td>
                        <td>{item.num_intersections}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              <div className="link-strip">
                {Object.entries(links).map(([label, href]) =>
                  href ? (
                    <a key={label} href={href} target="_blank" rel="noreferrer" className={`link-btn link-${label}`}>
                      {label === 'report' ? 'Report JSON' : label === 'reportPdf' ? 'Download PDF' : label === 'evidence' ? 'Evidence' : label === 'map' ? 'Map image' : label === 'ecParse' ? 'EC parse' : 'NDWI'}
                    </a>
                  ) : null,
                )}
              </div>

              <div className="analysis-box">
                <p className="eyebrow">Current summary</p>
                <div className="summary-line">
                  <strong>{summary.violations_found ?? 0}</strong>
                  <span>buffer checks flagged</span>
                </div>
                <div className="summary-line">
                  <strong>{summary.confidence ?? 'unknown'}</strong>
                  <span>confidence</span>
                </div>
              </div>

              <img id="preview" className="preview" alt="Run preview" style={{ display: 'none' }} />
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}

export default App;
