module.exports = async function handler(_req, res) {
  const backendUrl = process.env.RENDER_BACKEND_URL || "https://trafficdetect-vehicledetection-counting.onrender.com";
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify({ backendUrl }));
};
