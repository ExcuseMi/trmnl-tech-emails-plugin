/**
 * Tech Emails. Input: the polled emails.json (an array of records; a JSON string or { data: [...] } also works).
 * Output: { email, count, index } with ONE record, so the stored data stays small. Modes: random (a shuffle that
 * changes with the day, walked one step per 15 minute slot: no repeat until the list is through), newest,
 * on_this_day (same month and day in any year, else the nearest day of the year).
 * State (replaced by what we return): { recent: the last RECENT_MAX picked records (texts cut), i: where the
 * cached walk stands }. When the poll fails or holds no usable record, the cache is walked instead, so a GitHub
 * outage still shows emails; "No email" only when there never was a good result.
 */

var SLOT_MINUTES = 15;
var SLOTS_PER_DAY = 96;
var RECENT_MAX = 8;
var STATE_MAX_BYTES = 14000;
var DATE_RE = /^\d{4}(-\d{2}(-\d{2})?)?$/;

function str(v, max) {
  if (typeof v !== 'string') return '';
  var t = v.replace(/\s+/g, ' ').trim();
  return t.length > max ? t.slice(0, max - 1) + '…' : t;
}

function names(v) {
  if (!Array.isArray(v)) return [];
  return v.filter(function (x) { return typeof x === 'string' && x.trim(); }).map(function (x) { return str(x, 80); }).slice(0, 12);
}

/** A usable record, trimmed to what the views show; null for anything malformed. */
function clean(r) {
  if (!r || typeof r !== 'object' || Array.isArray(r)) return null;
  var date = typeof r.date === 'string' ? r.date.trim() : '';
  var from = str(r.from, 80), subject = str(r.subject, 200), excerpt = str(r.excerpt, 700);
  if (!from || !subject || !excerpt || !DATE_RE.test(date)) return null;
  var src = r.source && typeof r.source === 'object' ? r.source : {};
  return {
    from: from, to: names(r.to), cc: names(r.cc), date: date, subject: subject, excerpt: excerpt,
    context: str(r.context, 200), source: { title: str(src.title, 160) }
  };
}

function records(input) {
  var data = input && input.data;
  if (typeof data === 'string') { try { data = JSON.parse(data); } catch (e) { return []; } }
  if (data && !Array.isArray(data) && typeof data === 'object') data = data.data || data.emails;
  if (!Array.isArray(data)) return [];
  return data.map(clean).filter(Boolean);
}

function modeOf(input) {
  var cfv = (input && input.trmnl && input.trmnl.plugin_settings && input.trmnl.plugin_settings.custom_fields_values) || {};
  var m = String(cfv.mode || '').toLowerCase();
  return m === 'newest' || m === 'on_this_day' ? m : 'random';
}

function localNow(input) {
  var off = input && input.trmnl && input.trmnl.user && input.trmnl.user.utc_offset;
  var t = new Date(Date.now() + (Number.isFinite(off) ? off * 1000 : 0));
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate(), min: t.getUTCHours() * 60 + t.getUTCMinutes(),
           day: Math.floor(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()) / 86400000) };
}

/** Small seeded generator (mulberry32), so a shuffle is the same on every run of the same day. */
function rng(seed) {
  var a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    var t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffled(n, seed) {
  var a = [], i, r = rng(seed);
  for (i = 0; i < n; i++) a.push(i);
  for (i = n - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)), x = a[i]; a[i] = a[j]; a[j] = x; }
  return a;
}

/** The step of the walk: one per time slot, counted from the epoch. */
function step(now) { return now.day * SLOTS_PER_DAY + Math.floor(now.min / SLOT_MINUTES); }

function pickRandom(n, now) {
  var s = step(now), round = Math.floor(s / n);
  // the day's shuffle: its seed is the round, which starts on a new day for a list of up to 96 emails
  return shuffled(n, round * 2654435761 + n)[s % n];
}

function dayOfYear(m, d) { return [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][m - 1] + d; }

function pickOnThisDay(list, now) {
  var today = dayOfYear(now.m, now.d), best = [], bestDist = Infinity;
  list.forEach(function (r, i) {
    if (r.date.length < 7) return; // a year alone has no day
    var m = Number(r.date.slice(5, 7)), d = r.date.length >= 10 ? Number(r.date.slice(8, 10)) : 15;
    var diff = Math.abs(dayOfYear(m, Math.min(d, 28)) - today);
    var dist = Math.min(diff, 365 - diff);
    if (dist < bestDist) { bestDist = dist; best = [i]; } else if (dist === bestDist) best.push(i);
  });
  if (!best.length) return pickRandom(list.length, now);
  return best[step(now) % best.length];
}

function pickNewest(list) {
  var best = 0;
  list.forEach(function (r, i) {
    var pad = function (d) { return (d + '-12-31').slice(0, 10); };
    if (pad(r.date) > pad(list[best].date)) best = i;
  });
  return best;
}

function sameRecord(a, b) { return a.from === b.from && a.date === b.date && a.subject === b.subject; }

function boundedState(recent, i) {
  var list = recent.slice(-RECENT_MAX);
  while (list.length > 1 && JSON.stringify({ recent: list, i: i }).length > STATE_MAX_BYTES) list.shift();
  return { recent: list, i: Math.min(i, list.length - 1) };
}

function cleanState(s) {
  if (!s || typeof s !== 'object' || !Array.isArray(s.recent)) return { recent: [], i: 0 };
  var recent = s.recent.map(clean).filter(Boolean).slice(-RECENT_MAX);
  return { recent: recent, i: Number.isInteger(s.i) && s.i >= 0 ? s.i : 0 };
}

function run(input) {
  var state = cleanState(input && input.trmnl && input.trmnl.state);
  var list = records(input);
  if (list.length === 0) {
    // nothing usable from the poll: walk the cache; the state is handed back unchanged but for the position
    if (state.recent.length === 0) return { email: null, count: 0, index: 0, trmnl_state: state };
    var k = (state.i + 1) % state.recent.length;
    return { email: state.recent[k], count: state.recent.length, index: k + 1, stale: true, trmnl_state: { recent: state.recent, i: k } };
  }
  var now = localNow(input), mode = modeOf(input);
  var idx = mode === 'newest' ? pickNewest(list) : mode === 'on_this_day' ? pickOnThisDay(list, now) : pickRandom(list.length, now);
  var email = list[idx];
  var recent = state.recent.filter(function (r) { return !sameRecord(r, email); }).concat([email]);
  var next = boundedState(recent, recent.length - 1);
  return { email: email, count: list.length, index: idx + 1, trmnl_state: next };
}
