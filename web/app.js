// いい物件は7日まで - Client-side app

let allProperties = [];
let filteredProperties = [];
let map;
let markers = [];
let bookmarks = new Set();
let viewed = new Set();

var LS_FILTERS_KEY = "rental_filters";
var LS_BOOKMARKS_KEY = "rental_bookmarks";
var LS_VIEWED_KEY = "rental_viewed";

var WARD_COORDS = {
  "千代田区": [35.6940, 139.7536], "中央区": [35.6706, 139.7727],
  "港区": [35.6585, 139.7514], "新宿区": [35.6938, 139.7036],
  "文京区": [35.7081, 139.7522], "台東区": [35.7126, 139.7801],
  "墨田区": [35.7107, 139.8015], "江東区": [35.6729, 139.8173],
  "品川区": [35.6092, 139.7302], "目黒区": [35.6414, 139.6982],
  "大田区": [35.5613, 139.7160], "世田谷区": [35.6462, 139.6533],
  "渋谷区": [35.6640, 139.6982], "中野区": [35.7078, 139.6639],
  "杉並区": [35.6994, 139.6367], "豊島区": [35.7265, 139.7164],
  "北区": [35.7528, 139.7376], "荒川区": [35.7360, 139.7834],
  "板橋区": [35.7516, 139.7094], "練馬区": [35.7355, 139.6516],
  "足立区": [35.7752, 139.8044], "葛飾区": [35.7439, 139.8472],
  "江戸川区": [35.7068, 139.8684],
};

// Station coordinates for accurate map placement
var STATION_COORDS = {
  "新宿駅":[35.6896,139.7006],"新宿三丁目駅":[35.6884,139.7055],"新宿御苑前駅":[35.6879,139.7106],
  "新宿西口駅":[35.6942,139.6988],"西新宿駅":[35.6946,139.6922],"西新宿五丁目駅":[35.6908,139.6862],
  "都庁前駅":[35.6916,139.6917],"東新宿駅":[35.6971,139.7097],"新大久保駅":[35.7012,139.7001],
  "大久保駅":[35.7008,139.6971],"高田馬場駅":[35.7126,139.7038],"目白駅":[35.7211,139.7067],
  "早稲田駅":[35.7088,139.7219],"面影橋駅":[35.7115,139.7174],"神楽坂駅":[35.7020,139.7405],
  "牛込神楽坂駅":[35.7007,139.7355],"牛込柳町駅":[35.7000,139.7268],"若松河田駅":[35.6978,139.7198],
  "曙橋駅":[35.6924,139.7243],"四谷三丁目駅":[35.6876,139.7202],"四ツ谷駅":[35.6862,139.7303],
  "市ケ谷駅":[35.6914,139.7353],"飯田橋駅":[35.7022,139.7448],"江戸川橋駅":[35.7110,139.7335],
  "西早稲田駅":[35.7058,139.7092],"信濃町駅":[35.6816,139.7201],"千駄ケ谷駅":[35.6812,139.7117],
  "国立競技場駅":[35.6800,139.7139],"下落合駅":[35.7148,139.6946],"中井駅":[35.7140,139.6875],
  "落合駅":[35.7135,139.6884],"落合南長崎駅":[35.7217,139.6808],"東中野駅":[35.7076,139.6830],
  "中野駅":[35.7057,139.6654],"中野坂上駅":[35.6973,139.6774],"新中野駅":[35.6977,139.6644],
  "中野新橋駅":[35.6925,139.6632],"中野富士見町駅":[35.6879,139.6583],"方南町駅":[35.6833,139.6516],
  "新井薬師前駅":[35.7157,139.6666],"沼袋駅":[35.7193,139.6579],"野方駅":[35.7195,139.6483],
  "都立家政駅":[35.7210,139.6416],"鷺ノ宮駅":[35.7223,139.6346],"下井草駅":[35.7242,139.6266],
  "高円寺駅":[35.7052,139.6497],"東高円寺駅":[35.6985,139.6478],"新江古田駅":[35.7261,139.6739],
  "笹塚駅":[35.6740,139.6678],"幡ケ谷駅":[35.6767,139.6709],"幡ヶ谷駅":[35.6767,139.6709],
  "東長崎駅":[35.7269,139.6863],"椎名町駅":[35.7252,139.6952],"富士見台駅":[35.7337,139.6310],
  // 渋谷区
  "渋谷駅":[35.6580,139.7016],"恵比寿駅":[35.6467,139.7100],"代官山駅":[35.6488,139.7032],
  "中目黒駅":[35.6440,139.6990],"原宿駅":[35.6702,139.7027],"明治神宮前駅":[35.6699,139.7024],
  "表参道駅":[35.6653,139.7122],"外苑前駅":[35.6716,139.7176],"青山一丁目駅":[35.6727,139.7240],
  "代々木駅":[35.6833,139.7021],"代々木上原駅":[35.6680,139.6793],"代々木公園駅":[35.6682,139.6893],
  "代々木八幡駅":[35.6677,139.6879],"初台駅":[35.6787,139.6867],"参宮橋駅":[35.6773,139.6936],
  "南新宿駅":[35.6847,139.6992],"北参道駅":[35.6773,139.7052],"神泉駅":[35.6563,139.6934],
  "池尻大橋駅":[35.6506,139.6851],"駒場東大前駅":[35.6575,139.6840],
  "広尾駅":[35.6520,139.7222],"六本木駅":[35.6632,139.7316],
};

function resolveStationName(raw) {
  if (!raw) return null;
  // Try exact match first
  if (STATION_COORDS[raw]) return raw;
  // Extract station name from "路線名 駅名" format
  var m = raw.match(/\s+(.+駅)$/);
  if (m && STATION_COORDS[m[1]]) return m[1];
  // Try suffix match
  for (var name in STATION_COORDS) {
    if (raw.indexOf(name) !== -1) return name;
  }
  return null;
}

// --- Freshness helpers ---
function getDaysAge(firstSeen) {
  if (!firstSeen) return 99;
  var diff = Date.now() - new Date(firstSeen).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function getFreshnessLabel(days) {
  if (days <= 1) return "NEW";
  return days + "日目";
}

function getFreshnessClass(days) {
  if (days <= 2) return "freshness-new";
  if (days <= 5) return "freshness-mid";
  return "freshness-old";
}

// --- Bookmarks (localStorage) ---
function loadBookmarks() {
  try {
    var raw = localStorage.getItem(LS_BOOKMARKS_KEY);
    if (raw) bookmarks = new Set(JSON.parse(raw));
  } catch (e) { /* ignore */ }
}

function saveBookmarks() {
  localStorage.setItem(LS_BOOKMARKS_KEY, JSON.stringify(Array.from(bookmarks)));
}

// --- Viewed history (localStorage) ---
function loadViewed() {
  try {
    var raw = localStorage.getItem(LS_VIEWED_KEY);
    if (raw) viewed = new Set(JSON.parse(raw));
  } catch (e) { /* ignore */ }
}

function saveViewed() {
  localStorage.setItem(LS_VIEWED_KEY, JSON.stringify(Array.from(viewed)));
}

function markViewed(id) {
  if (!viewed.has(id)) {
    viewed.add(id);
    saveViewed();
  }
}

function toggleBookmark(id, e) {
  e.stopPropagation();
  if (bookmarks.has(id)) {
    bookmarks.delete(id);
  } else {
    bookmarks.add(id);
  }
  saveBookmarks();
  renderList();
  renderMap();
}

// --- Filter persistence (localStorage) ---
function saveFilters() {
  var state = {
    rentMin: document.getElementById("rent-min").value,
    rentMax: document.getElementById("rent-max").value,
    daysMin: document.getElementById("days-min").value,
    daysMax: document.getElementById("days-max").value,
    walkMax: document.getElementById("walk-max").value,
    ageMax: document.getElementById("age-max").value,
    sizeMin: document.getElementById("size-min").value,
    keyword: document.getElementById("keyword").value,
    bookmarkOnly: document.getElementById("bookmark-only").checked,
    hideViewed: document.getElementById("hide-viewed").checked,
    mapBoundsOnly: !!(document.getElementById("map-bounds-only") &&
      document.getElementById("map-bounds-only").checked),
    sort: document.getElementById("sort-select").value,
    layouts: getCheckedValues("layout-checks"),
    sources: getCheckedValues("source-checks"),
  };
  localStorage.setItem(LS_FILTERS_KEY, JSON.stringify(state));
}

function restoreFilters() {
  try {
    var raw = localStorage.getItem(LS_FILTERS_KEY);
    if (!raw) return;
    var state = JSON.parse(raw);

    if (state.rentMin) document.getElementById("rent-min").value = state.rentMin;
    if (state.rentMax) document.getElementById("rent-max").value = state.rentMax;
    if (state.daysMin) document.getElementById("days-min").value = state.daysMin;
    if (state.daysMax) document.getElementById("days-max").value = state.daysMax;
    if (state.walkMax) document.getElementById("walk-max").value = state.walkMax;
    if (state.ageMax) document.getElementById("age-max").value = state.ageMax;
    if (state.sizeMin) document.getElementById("size-min").value = state.sizeMin;
    if (state.keyword) document.getElementById("keyword").value = state.keyword;
    if (state.bookmarkOnly) document.getElementById("bookmark-only").checked = true;
    if (state.hideViewed) document.getElementById("hide-viewed").checked = true;
    var boundsOnly = document.getElementById("map-bounds-only");
    if (boundsOnly && typeof state.mapBoundsOnly === "boolean") {
      boundsOnly.checked = state.mapBoundsOnly;
    }
    if (state.sort) document.getElementById("sort-select").value = state.sort;

    // Restore layout checkboxes
    if (state.layouts && state.layouts.length > 0) {
      document.querySelectorAll("#layout-checks input").forEach(function(cb) {
        cb.checked = state.layouts.indexOf(cb.value) !== -1;
      });
    }

    // Source checkboxes are built dynamically after data loads,
    // so we store the values and apply them after build
    restoreFilters._pendingSources = state.sources || [];
  } catch (e) { /* ignore */ }
}
restoreFilters._pendingSources = [];

function applyPendingDynamicFilters() {
  if (restoreFilters._pendingSources.length > 0) {
    document.querySelectorAll("#source-checks input").forEach(function(cb) {
      cb.checked = restoreFilters._pendingSources.indexOf(cb.value) !== -1;
    });
  }
}

// --- Init ---
document.addEventListener("DOMContentLoaded", async function() {
  loadBookmarks();
  loadViewed();
  initMap();
  await loadData();
  restoreFilters();
  setupFilters();
  applyPendingDynamicFilters();
  applyFilters();
});

function initMap() {
  map = L.map("map").setView([35.6812, 139.7671], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(map);

  // Re-filter list as the user pans/zooms. Debounced so dragging stays smooth.
  var debouncedViewChange = debounce(onMapViewChanged, 120);
  map.on("moveend", debouncedViewChange);
  map.on("zoomend", debouncedViewChange);
}

async function loadData() {
  try {
    var resp = await fetch("/api/properties");
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    allProperties = await resp.json();

    allProperties.forEach(function(p) {
      if (!p.lat || !p.lng) {
        // Try station coordinates first (accurate within ~200m)
        var stName = resolveStationName(p.nearest_station);
        if (stName && STATION_COORDS[stName]) {
          var sc = STATION_COORDS[stName];
          var walk = p.walk_minutes || 5;
          var spread = Math.min(walk, 15) * 0.0008; // ~80m per walk minute
          p.lat = sc[0] + (Math.random() - 0.5) * spread;
          p.lng = sc[1] + (Math.random() - 0.5) * spread;
        } else if (p.ward && WARD_COORDS[p.ward]) {
          // Fallback: ward center with wider spread
          var coords = WARD_COORDS[p.ward];
          p.lat = coords[0] + (Math.random() - 0.5) * 0.035;
          p.lng = coords[1] + (Math.random() - 0.5) * 0.035;
        }
      }
      p._daysAge = getDaysAge(p.first_seen);
    });

    document.getElementById("count-badge").textContent = allProperties.length + "件";

    if (allProperties.length > 0 && allProperties[0].last_seen) {
      var d = new Date(allProperties[0].last_seen);
      document.getElementById("last-fetch").textContent =
        "最終取得: " + (d.getMonth()+1) + "/" + d.getDate() + " " +
        d.getHours() + ":" + String(d.getMinutes()).padStart(2, "0");
    }

    buildSourceChecks();

  } catch (e) {
    console.error("Failed to load data:", e);
    var msg = document.createElement("p");
    msg.style.cssText = "padding:20px;color:#999";
    msg.textContent = "データがありません。python main.py fetch を実行してください。";
    document.getElementById("property-list").appendChild(msg);
  }
}

function buildSourceChecks() {
  var sources = [];
  var seen = {};
  allProperties.forEach(function(p) {
    if (p.source && !seen[p.source]) { sources.push(p.source); seen[p.source] = true; }
  });
  sources.sort();
  var container = document.getElementById("source-checks");
  container.replaceChildren();
  sources.forEach(function(s) {
    var label = document.createElement("label");
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = s;
    cb.addEventListener("change", applyFilters);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(s));
    container.appendChild(label);
  });
}

// --- Filtering ---
function setupFilters() {
  var inputs = ["rent-min", "rent-max", "days-min", "days-max", "walk-max", "age-max", "size-min", "keyword"];
  inputs.forEach(function(id) {
    document.getElementById(id).addEventListener("input", debounce(applyFilters, 300));
  });

  document.getElementById("sort-select").addEventListener("change", applyFilters);
  document.getElementById("bookmark-only").addEventListener("change", applyFilters);
  document.getElementById("hide-viewed").addEventListener("change", applyFilters);

  var boundsOnly = document.getElementById("map-bounds-only");
  if (boundsOnly) {
    boundsOnly.addEventListener("change", function() {
      saveFilters();
      renderList();
    });
  }

  document.querySelectorAll("#layout-checks input").forEach(function(cb) {
    cb.addEventListener("change", applyFilters);
  });
}

function getCheckedValues(containerId) {
  var checks = document.querySelectorAll("#" + containerId + " input:checked");
  return Array.from(checks).map(function(c) { return c.value; });
}

function applyFilters() {
  var rentMin = parseFloat(document.getElementById("rent-min").value) * 10000 || 0;
  var rentMax = parseFloat(document.getElementById("rent-max").value) * 10000 || Infinity;
  var daysMinRaw = document.getElementById("days-min").value;
  var daysMaxRaw = document.getElementById("days-max").value;
  var daysMin = daysMinRaw === "" ? 0 : parseInt(daysMinRaw);
  var daysMax = daysMaxRaw === "" ? Infinity : parseInt(daysMaxRaw);
  var walkMax = parseInt(document.getElementById("walk-max").value) || Infinity;
  var ageMax = parseInt(document.getElementById("age-max").value) || Infinity;
  var sizeMin = parseFloat(document.getElementById("size-min").value) || 0;
  var keyword = document.getElementById("keyword").value.toLowerCase().trim();
  var bookmarkOnly = document.getElementById("bookmark-only").checked;
  var hideViewed = document.getElementById("hide-viewed").checked;
  var layouts = getCheckedValues("layout-checks");
  var sources = getCheckedValues("source-checks");

  filteredProperties = allProperties.filter(function(p) {
    if (bookmarkOnly && !bookmarks.has(p.id)) return false;
    if (hideViewed && viewed.has(p.id)) return false;
    if (p.rent < rentMin || p.rent > rentMax) return false;
    if (p._daysAge < daysMin || p._daysAge > daysMax) return false;
    if (p.walk_minutes != null && p.walk_minutes > walkMax) return false;
    if (p.building_age_years != null && p.building_age_years > ageMax) return false;
    if (p.size_sqm != null && p.size_sqm < sizeMin) return false;
    if (layouts.length > 0 && layouts.indexOf(p.layout) === -1) return false;
    if (sources.length > 0 && sources.indexOf(p.source) === -1) return false;
    if (keyword) {
      var text = [p.name, p.address, p.nearest_station, p.line].join(" ").toLowerCase();
      if (text.indexOf(keyword) === -1) return false;
    }
    return true;
  });

  var sort = document.getElementById("sort-select").value;
  sortProperties(filteredProperties, sort);

  saveFilters();
  renderMap();      // plot every marker the filter allows
  renderList();     // renderList further narrows to current map bounds
}

// Pan/zoom the map without redrawing markers: just re-filter the list to the
// properties whose markers are currently visible.
function onMapViewChanged() {
  if (document.getElementById("map-bounds-only") && document.getElementById("map-bounds-only").checked) {
    renderList();
  }
}

function propertiesVisibleOnMap() {
  var boundsOnly = document.getElementById("map-bounds-only");
  if (!boundsOnly || !boundsOnly.checked || !map) {
    return filteredProperties;
  }
  var bounds = map.getBounds();
  return filteredProperties.filter(function(p) {
    if (!p.lat || !p.lng) return false;
    return bounds.contains([p.lat, p.lng]);
  });
}

function sortProperties(props, sort) {
  switch (sort) {
    case "freshness":
      props.sort(function(a, b) {
        return a._daysAge - b._daysAge || a.rent - b.rent;
      });
      break;
    case "rent-asc":
      props.sort(function(a, b) { return a.rent - b.rent; });
      break;
    case "rent-desc":
      props.sort(function(a, b) { return b.rent - a.rent; });
      break;
    case "size-desc":
      props.sort(function(a, b) { return (b.size_sqm || 0) - (a.size_sqm || 0); });
      break;
    case "age-asc":
      props.sort(function(a, b) {
        return (a.building_age_years != null ? a.building_age_years : 99) -
               (b.building_age_years != null ? b.building_age_years : 99);
      });
      break;
    case "walk-asc":
      props.sort(function(a, b) {
        return (a.walk_minutes != null ? a.walk_minutes : 99) -
               (b.walk_minutes != null ? b.walk_minutes : 99);
      });
      break;
  }
}

function resetFilters() {
  document.getElementById("rent-min").value = "";
  document.getElementById("rent-max").value = "";
  document.getElementById("days-min").value = "";
  document.getElementById("days-max").value = "";
  document.getElementById("walk-max").value = "";
  document.getElementById("age-max").value = "";
  document.getElementById("size-min").value = "";
  document.getElementById("keyword").value = "";
  document.getElementById("bookmark-only").checked = false;
  document.getElementById("hide-viewed").checked = false;
  document.getElementById("sort-select").value = "freshness";
  document.querySelectorAll("#layout-checks input, #source-checks input")
    .forEach(function(cb) { cb.checked = false; });
  applyFilters();
}

// --- Rendering ---
function formatRent(yen) {
  if (yen >= 10000) {
    var man = yen / 10000;
    return (yen % 10000 === 0 ? man.toFixed(0) : man.toFixed(1)) + "万円";
  }
  return yen.toLocaleString() + "円";
}

function renderList() {
  var container = document.getElementById("property-list");
  container.replaceChildren();

  var visible = propertiesVisibleOnMap();
  var boundsOnly = document.getElementById("map-bounds-only") &&
    document.getElementById("map-bounds-only").checked;
  var countLabel = visible.length + "件表示";
  if (boundsOnly && visible.length !== filteredProperties.length) {
    countLabel += " (全 " + filteredProperties.length + "件中)";
  }
  document.getElementById("filtered-count").textContent = countLabel;

  if (visible.length === 0) {
    var msg = document.createElement("p");
    msg.style.cssText = "padding:20px;color:#999;text-align:center";
    msg.textContent = boundsOnly
      ? "この地図範囲内には物件がありません（地図を移動/縮小するか、チェックを外してください）"
      : "条件に合う物件がありません";
    container.appendChild(msg);
    return;
  }

  var toRender = visible.slice(0, 200);
  toRender.forEach(function(p) {
    var card = createPropertyCard(p);
    container.appendChild(card);
  });

  if (visible.length > 200) {
    var more = document.createElement("p");
    more.style.cssText = "padding:12px;color:#999;text-align:center";
    more.textContent = "他 " + (visible.length - 200) + " 件...";
    container.appendChild(more);
  }
}

function createPropertyCard(p) {
  var days = p._daysAge;
  var isBookmarked = bookmarks.has(p.id);
  var isViewed = viewed.has(p.id);
  var card = document.createElement("div");
  card.className = "property-card " + getFreshnessClass(days) + (isViewed ? " viewed" : "");
  card.addEventListener("click", function() {
    markViewed(p.id);
    card.classList.add("viewed");
    window.open(p.source_url, "_blank");
  });

  // Image
  if (p.image_url) {
    var img = document.createElement("img");
    img.className = "card-image";
    img.src = p.image_url;
    img.alt = "";
    img.loading = "lazy";
    img.onerror = function() { this.style.display = "none"; };
    card.appendChild(img);
  }

  // Body
  var body = document.createElement("div");
  body.className = "card-body";

  // Title row: freshness badge + name + bookmark button
  var titleDiv = document.createElement("div");
  titleDiv.className = "card-title";

  var badge = document.createElement("span");
  badge.className = "freshness-badge " + getFreshnessClass(days);
  badge.textContent = getFreshnessLabel(days);
  titleDiv.appendChild(badge);

  var nameSpan = document.createElement("span");
  nameSpan.className = "name";
  nameSpan.textContent = p.name || "";
  titleDiv.appendChild(nameSpan);

  // Bookmark button
  var bmBtn = document.createElement("button");
  bmBtn.className = "btn-bookmark" + (isBookmarked ? " bookmarked" : "");
  bmBtn.textContent = isBookmarked ? "\u2605" : "\u2606";
  bmBtn.title = isBookmarked ? "ブックマーク解除" : "ブックマーク";
  bmBtn.addEventListener("click", function(e) { toggleBookmark(p.id, e); });
  titleDiv.appendChild(bmBtn);

  body.appendChild(titleDiv);

  // Rent
  var rentDiv = document.createElement("div");
  rentDiv.className = "card-rent";
  rentDiv.textContent = formatRent(p.rent);
  if (p.management_fee) {
    var admin = document.createElement("span");
    admin.className = "admin";
    admin.textContent = "+" + formatRent(p.management_fee);
    rentDiv.appendChild(admin);
  }
  body.appendChild(rentDiv);

  // Details
  var details = [
    p.layout,
    p.size_sqm ? p.size_sqm + "㎡" : null,
    p.floor ? p.floor + "階" : null,
    p.building_age_years != null ? "築" + p.building_age_years + "年" : null,
    p.structure || null,
  ].filter(Boolean).join(" / ");

  var depositParts = [];
  if (p.deposit != null) depositParts.push("敷" + formatRent(p.deposit));
  if (p.key_money != null) depositParts.push("礼" + formatRent(p.key_money));
  var depositText = depositParts.join(" ");

  var detailDiv = document.createElement("div");
  detailDiv.className = "card-details";
  var detailSpan = document.createElement("span");
  detailSpan.textContent = details;
  detailDiv.appendChild(detailSpan);
  if (depositText) {
    var depSpan = document.createElement("span");
    depSpan.textContent = depositText;
    detailDiv.appendChild(depSpan);
  }
  body.appendChild(detailDiv);

  // Location
  var locDiv = document.createElement("div");
  locDiv.className = "card-location";
  locDiv.textContent = (p.address || "") + " / " + (p.nearest_station || "") +
    " 徒歩" + (p.walk_minutes != null ? p.walk_minutes : "?") + "分 (" + (p.line || "") + ")";
  body.appendChild(locDiv);

  // Source
  var srcDiv = document.createElement("div");
  srcDiv.className = "card-source";
  srcDiv.textContent = p.source;
  body.appendChild(srcDiv);

  card.appendChild(body);
  return card;
}

// Kept true on first render so the map auto-fits to the full result set once.
// After that we leave the user's pan/zoom alone so the map-bounds list filter
// and every subsequent filter edit doesn't yank the viewport around.
var shouldAutoFitBounds = true;

function renderMap() {
  markers.forEach(function(m) { map.removeLayer(m); });
  markers = [];

  var withCoords = filteredProperties.filter(function(p) { return p.lat && p.lng; });
  // No hard cap — Leaflet handles ~10k markers fine, and the old 500 cap was
  // silently dropping most pins once results exceeded that.
  var toPlot = withCoords;

  toPlot.forEach(function(p) {
    var days = Math.min(p._daysAge, 6);
    var isBookmarked = bookmarks.has(p.id);
    var isViewed = viewed.has(p.id);
    var color = isViewed ? "#888" : (days <= 1 ? "#00c853" : days <= 3 ? "#ffab00" : "#ff1744");
    var size = 26;
    var opacity = isViewed ? "opacity:0.55;" : "";
    var bmRing = isBookmarked ? "box-shadow:0 0 0 3px #ffd600,0 2px 6px rgba(0,0,0,0.4);" : "box-shadow:0 2px 6px rgba(0,0,0,0.4);";
    var label = days <= 0 ? "N" : String(days);
    var icon = L.divIcon({
      className: "marker-day",
      html: '<div style="' + opacity + 'width:' + size + 'px;height:' + size + 'px;background:' + color + ';border:2px solid #fff;border-radius:50%;' + bmRing + 'display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:13px;line-height:1;">' + label + '</div>',
      iconSize: [size, size],
      iconAnchor: [size/2, size/2],
    });

    var marker = L.marker([p.lat, p.lng], { icon: icon }).addTo(map);

    var popupDiv = document.createElement("div");

    var title = document.createElement("div");
    title.className = "popup-title";
    title.textContent = (isBookmarked ? "\u2605 " : "") + (p.name || "");
    popupDiv.appendChild(title);

    var freshBadge = document.createElement("span");
    freshBadge.className = "freshness-badge " + getFreshnessClass(days);
    freshBadge.textContent = getFreshnessLabel(days);
    popupDiv.appendChild(freshBadge);

    var rent = document.createElement("div");
    rent.className = "popup-rent";
    rent.textContent = formatRent(p.rent);
    popupDiv.appendChild(rent);

    var detail = document.createElement("div");
    detail.className = "popup-detail";
    detail.textContent = (p.layout || "") + " " + (p.size_sqm || "") + "㎡ / " +
      (p.nearest_station || "") + " 徒歩" + (p.walk_minutes != null ? p.walk_minutes : "?") + "分";
    popupDiv.appendChild(detail);

    var linkDiv = document.createElement("div");
    linkDiv.className = "popup-link";
    var link = document.createElement("a");
    link.href = p.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "詳細を見る";
    link.addEventListener("click", function() {
      markViewed(p.id);
      renderList();
    });
    linkDiv.appendChild(link);
    popupDiv.appendChild(linkDiv);

    marker.bindPopup(popupDiv);
    markers.push(marker);
  });

  if (markers.length > 0 && shouldAutoFitBounds) {
    var group = L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.1));
    shouldAutoFitBounds = false;
  }
}

// --- Utils ---
function debounce(fn, ms) {
  var timer;
  return function() {
    var args = arguments;
    var context = this;
    clearTimeout(timer);
    timer = setTimeout(function() { fn.apply(context, args); }, ms);
  };
}
