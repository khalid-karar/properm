// API location.
//  - FastAPI serves this UI: leave PROPERM_API empty.
//  - UI on another host: set PROPERM_API to the API address (and allow this origin with PROPERM_CORS_ORIGINS).
//  - Static demo hosting (Netlify): the Python backend runs in the browser, in-memory, seeded with demo data.
window.PROPERM_API = "";
window.PROPERM_EMBEDDED = !window.PROPERM_API && (/\.netlify\.app$/.test(location.hostname) || new URLSearchParams(location.search).has("embedded"));
