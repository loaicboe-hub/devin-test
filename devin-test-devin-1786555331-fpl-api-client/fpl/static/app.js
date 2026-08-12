const PLAYER_COLUMNS = [
  { key: "name", label: "Player", sort: null },
  { key: "position", label: "Pos", sort: null },
  { key: "team", label: "Club", sort: null },
  { key: "cost", label: "£m", sort: "cost", format: (v) => v.toFixed(1) },
  { key: "total_points", label: "Pts", sort: "points" },
  { key: "points_per_game", label: "PPG", sort: "ppg" },
  { key: "form", label: "Form", sort: "form" },
  { key: "value", label: "Pts/£m", sort: "value" },
  { key: "expected_goal_involvements", label: "xGI", sort: "xgi" },
  { key: "ict_index", label: "ICT", sort: "ict" },
  { key: "selected_by_percent", label: "Own%", sort: "ownership" },
];

const state = {
  view: "players",
  rows: [],
  columns: PLAYER_COLUMNS,
  refresh: false,
};

const $ = (id) => document.getElementById(id);
const results = $("results");

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined && value !== false) {
      search.set(key, value);
    }
  });
  if (state.refresh) search.set("refresh", "1");
  return search.toString();
}

async function fetchJson(path, params) {
  const response = await fetch(`${path}?${query(params)}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `request failed (${response.status})`);
  return payload;
}

function playerFilters() {
  const maxCost = Number($("max-cost").value);
  return {
    position: $("position").value,
    team: $("team").value,
    sort: $("sort").value,
    max_cost: maxCost >= Number($("max-cost").max) ? "" : maxCost,
    min_minutes: $("min-minutes").value,
    limit: $("limit").value,
    available_only: $("available-only").checked,
  };
}

function renderTable(rows, columns, sortKey) {
  if (!rows.length) {
    results.innerHTML = '<div class="empty">No players match these filters.</div>';
    return;
  }
  const head = columns
    .map(
      (col) =>
        `<th data-sort="${col.sort || ""}" class="${col.sort && col.sort === sortKey ? "sorted" : ""}">${col.label}</th>`,
    )
    .join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((col) => {
          const raw = row[col.key];
          if (col.key === "name") {
            const flag = row.news
              ? `<span class="flag" title="${escapeHtml(row.news)}">&#9888;</span>`
              : "";
            return `<td><div class="player-cell"><span>${escapeHtml(raw)}${flag}</span><span class="full">${escapeHtml(row.full_name)}</span></div></td>`;
          }
          if (col.key === "position") {
            return `<td><span class="pos ${raw}">${raw}</span></td>`;
          }
          return `<td>${col.format ? col.format(raw) : raw}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  results.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  results.querySelectorAll("th[data-sort]").forEach((th) => {
    const key = th.dataset.sort;
    if (!key) return;
    th.addEventListener("click", () => {
      $("sort").value = key;
      load();
    });
  });
}

function renderTeams(teams) {
  const max = Math.max(...teams.map((t) => t.points), 1);
  const rows = teams
    .map(
      (team, index) => `
        <tr>
          <td>${index + 1}</td>
          <td>${team.team}</td>
          <td>${team.points}</td>
          <td><div class="bar"><span style="width:${(team.points / max) * 100}%"></span></div></td>
        </tr>`,
    )
    .join("");
  results.innerHTML = `<table><thead><tr><th>#</th><th>Club</th><th>Points</th><th>Share</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
  );
}

async function load() {
  results.innerHTML = '<div class="empty">Loading analytics…</div>';
  try {
    if (state.view === "players") {
      const filters = playerFilters();
      const data = await fetchJson("/api/players", filters);
      state.rows = data.players;
      state.columns = PLAYER_COLUMNS;
      renderTable(data.players, PLAYER_COLUMNS, data.sort);
      $("result-count").textContent = `${data.players.length} of ${data.total} players`;
    } else if (state.view === "differentials") {
      const data = await fetchJson("/api/differentials", {
        max_ownership: $("max-ownership").value,
        limit: $("diff-limit").value,
      });
      state.rows = data.players;
      state.columns = PLAYER_COLUMNS;
      renderTable(data.players, PLAYER_COLUMNS, "form");
      $("result-count").textContent = `${data.players.length} differentials`;
    } else {
      const data = await fetchJson("/api/teams", {});
      state.rows = data.teams;
      state.columns = [
        { key: "team", label: "Club" },
        { key: "points", label: "Points" },
      ];
      renderTeams(data.teams);
      $("result-count").textContent = `${data.teams.length} clubs`;
    }
  } catch (error) {
    results.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
    $("result-count").textContent = "";
  } finally {
    state.refresh = false;
  }
}

function exportCsv() {
  if (!state.rows.length) return;
  const columns = state.columns.map((col) => col.key);
  const lines = [columns.join(",")];
  state.rows.forEach((row) => {
    lines.push(columns.map((key) => `"${String(row[key] ?? "").replace(/"/g, '""')}"`).join(","));
  });
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: `fpl-${state.view}.csv` });
  link.click();
  URL.revokeObjectURL(url);
}

function renderCards(status) {
  $("cards").innerHTML = [
    { label: "Players", value: status.player_count, sub: `${status.team_count} clubs` },
    {
      label: "Gameweek",
      value: status.current_gameweek || "Pre-season",
      sub: status.next_gameweek ? `Next: ${status.next_gameweek}` : "",
    },
    {
      label: "Next deadline",
      value: status.next_deadline
        ? new Date(status.next_deadline).toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
          })
        : "—",
      sub: status.next_deadline ? new Date(status.next_deadline).toLocaleTimeString() : "",
    },
    { label: "Source", value: "Official API", sub: "Cached locally · 15 min" },
  ]
    .map(
      (card) =>
        `<div class="card"><div class="label">${card.label}</div><div class="value">${escapeHtml(card.value)}</div><div class="sub">${escapeHtml(card.sub)}</div></div>`,
    )
    .join("");
  $("gw-summary").textContent = status.next_deadline
    ? `Next deadline ${new Date(status.next_deadline).toLocaleString()}`
    : "Season data loaded";
}

async function init() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
      state.view = tab.dataset.view;
      document.querySelectorAll("[data-view-filters]").forEach((group) => {
        group.classList.toggle("hidden", group.dataset.viewFilters !== state.view);
      });
      load();
    });
  });

  $("max-cost").addEventListener("input", (event) => {
    const value = Number(event.target.value);
    $("max-cost-value").textContent = value >= Number(event.target.max) ? "any" : `£${value.toFixed(1)}m`;
  });
  $("max-ownership").addEventListener("input", (event) => {
    $("max-ownership-value").textContent = `${event.target.value}%`;
  });

  ["position", "team", "sort", "limit", "min-minutes", "available-only", "diff-limit"].forEach(
    (id) => $(id).addEventListener("change", load),
  );
  ["max-cost", "max-ownership"].forEach((id) => $(id).addEventListener("change", load));

  $("export").addEventListener("click", exportCsv);
  $("refresh").addEventListener("click", async (event) => {
    event.target.disabled = true;
    state.refresh = true;
    await load();
    event.target.disabled = false;
  });

  try {
    const status = await fetchJson("/api/status", {});
    renderCards(status);
    status.positions.forEach((position) =>
      $("position").add(new Option(position, position)),
    );
    status.teams.forEach((team) => $("team").add(new Option(team, team)));
    status.sort_keys.forEach((key) => $("sort").add(new Option(key.replace("_", " "), key)));
    $("sort").value = "points";
  } catch (error) {
    $("gw-summary").textContent = error.message;
  }
  load();
}

init();
