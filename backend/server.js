/**
 * Backend - Python ai-service'i (FastAPI, port 8000) proxy'ler, ve build
 * edilmis React frontend'ini (frontend/dist) statik olarak sunar.
 *
 * Neden proxy? Cunku gercek hayatta frontend'in Python servisiyle dogrudan
 * konusmasi istenmez (CORS/guvenlik/versiyonlama acisindan). Node backend
 * bu ikisi arasinda bir "gateway" katmani - Atez gibi sirketlerin de
 * kullandigi tipik mimari (.NET/Node.js + Python AI servisi).
 *
 * Calistirmak icin:
 *   npm install
 *   npm start
 * Sonra taraycida: http://localhost:3000
 *
 * ONEMLI: Python ai-service'i (uvicorn app.main:app --port 8000) once
 * ayri bir terminalde calisiyor olmali, yoksa /api/* istekleri hata doner.
 */

const express = require("express");
const path = require("path");
const fs = require("fs");

const app = express();
app.use(express.json());

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";
const PORT = process.env.PORT || 3000;

function aiServisineIlet(pythonYolu) {
  return async (req, res) => {
    try {
      const yanit = await fetch(`${AI_SERVICE_URL}${pythonYolu}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req.body),
      });
      const veri = await yanit.json();
      res.status(yanit.status).json(veri);
    } catch (err) {
      res.status(502).json({
        hata: "Yapay zeka servisine ulasilamiyor. Python servisinin (uvicorn) calistigindan emin ol.",
        detay: err.message,
        beklenen_adres: AI_SERVICE_URL,
      });
    }
  };
}

app.get("/api/health", async (req, res) => {
  try {
    const yanit = await fetch(`${AI_SERVICE_URL}/`);
    const veri = await yanit.json();
    res.json({ backend: "calisiyor", ai_service: veri });
  } catch (err) {
    res.status(503).json({ backend: "calisiyor", ai_service: "erisilemiyor", detay: err.message });
  }
});

app.post("/api/risk-analizi", aiServisineIlet("/risk-analizi"));
app.post("/api/oneri", aiServisineIlet("/oneri"));
app.post("/api/feedback", aiServisineIlet("/feedback"));

// Build edilmis React frontend'ini sun
const frontendDist = path.join(__dirname, "..", "frontend", "dist");
if (fs.existsSync(frontendDist)) {
  app.use(express.static(frontendDist));
  // Express 5'te bare "*" path-to-regexp hatasi verebiliyor, bu yuzden
  // path belirtmeden genel bir middleware kullaniyoruz (SPA client-side
  // routing icin son care - tum eslesmeyen GET istekleri index.html'e duser).
  app.use((req, res) => {
    res.sendFile(path.join(frontendDist, "index.html"));
  });
} else {
  app.use((req, res) => {
    res.status(404).send(
      "Frontend build bulunamadi. 'cd frontend && npm install && npm run build' calistirip tekrar dene."
    );
  });
}

app.listen(PORT, () => {
  console.log(`Backend calisiyor: http://localhost:${PORT}`);
  console.log(`AI servisi (Python) adresi: ${AI_SERVICE_URL}`);
});