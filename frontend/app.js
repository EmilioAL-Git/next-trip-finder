const API_SEARCH_URL = "/api/search";

const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const submitBtn = document.getElementById("submit-btn");

function parseDestinations(raw) {
  return raw
    .split(",")
    .map((code) => code.trim().toUpperCase())
    .filter(Boolean);
}

function timeWindowFrom(fromId, toId) {
  const from = document.getElementById(fromId).value;
  const to = document.getElementById(toId).value;
  if (!from || !to) return null;
  return { from_time: from, to_time: to };
}

function buildRequestBody(formData) {
  const body = {
    origin: formData.get("origin").trim().toUpperCase(),
    destinations: parseDestinations(formData.get("destinations") || ""),
    outbound_date_from: formData.get("outbound_date_from"),
    outbound_date_to: formData.get("outbound_date_to"),
    return_date_from: formData.get("return_date_from"),
    return_date_to: formData.get("return_date_to"),
    currency: formData.get("currency"),
    max_results: Number(formData.get("max_results")) || 50,
  };

  const minNights = formData.get("min_nights");
  const maxNights = formData.get("max_nights");
  if (minNights) body.min_nights = Number(minNights);
  if (maxNights) body.max_nights = Number(maxNights);

  const outboundWindow = timeWindowFrom("outbound_time_from", "outbound_time_to");
  if (outboundWindow) body.outbound_departure_window = outboundWindow;

  const returnWindow = timeWindowFrom("return_time_from", "return_time_to");
  if (returnWindow) body.return_departure_window = returnWindow;

  return body;
}

function formatDateTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderResults(data) {
  if (!data.results.length) {
    resultsEl.innerHTML = "<p>No se han encontrado combinaciones que cumplan tus criterios.</p>";
    return;
  }

  const rows = data.results
    .map((combo) => {
      const bookCell = combo.booking_url
        ? `<a class="book-link" href="${combo.booking_url}" target="_blank" rel="noopener">Reservar</a>`
        : "—";
      return `
        <tr>
          <td>${combo.destination_city || combo.destination_code}</td>
          <td>${formatDateTime(combo.outbound.departure)}</td>
          <td>${formatDateTime(combo.outbound.arrival)}</td>
          <td>${combo.outbound.stops}</td>
          <td>${formatDateTime(combo.inbound.departure)}</td>
          <td>${formatDateTime(combo.inbound.arrival)}</td>
          <td>${combo.inbound.stops}</td>
          <td>${combo.nights}</td>
          <td>${[...new Set([...combo.outbound.airlines, ...combo.inbound.airlines])].join(", ")}</td>
          <td class="price">${combo.price.toFixed(2)} ${combo.currency}</td>
          <td>${bookCell}</td>
        </tr>`;
    })
    .join("");

  resultsEl.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Destino</th>
          <th>Salida ida</th>
          <th>Llegada ida</th>
          <th>Escalas ida</th>
          <th>Salida vuelta</th>
          <th>Llegada vuelta</th>
          <th>Escalas vuelta</th>
          <th>Noches</th>
          <th>Aerolíneas</th>
          <th>Precio</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Buscando combinaciones...";
  statusEl.classList.remove("error");
  resultsEl.innerHTML = "";
  submitBtn.disabled = true;

  try {
    const body = buildRequestBody(new FormData(form));
    const response = await fetch(API_SEARCH_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload.detail || `Error ${response.status}`);
    }

    const data = await response.json();
    statusEl.textContent = `${data.count} combinaciones encontradas.`;
    renderResults(data);
  } catch (error) {
    statusEl.textContent = `No se pudo completar la búsqueda: ${error.message}`;
    statusEl.classList.add("error");
  } finally {
    submitBtn.disabled = false;
  }
});
