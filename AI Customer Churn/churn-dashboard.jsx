import React, { useState, useMemo, useEffect } from "react";
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  Activity, Search, LogOut, LayoutDashboard, Users, FileText,
  AlertTriangle, Sparkles, Building2, ShoppingCart, Tv, Smartphone,
  ChevronRight, X, ArrowLeft, ShieldCheck, TrendingDown, Download,
} from "lucide-react";

/* ---------------------------------------------------------------
   DESIGN TOKENS — "Vitals" system
   Concept: a company monitors customer health like a hospital
   monitors vital signs. Risk score = pulse. Churning customer =
   flatlining. Everything reads like a signal room, not a generic
   SaaS dashboard.
----------------------------------------------------------------*/
const COLORS = {
  ink: "#0B0E14",
  panel: "#12161F",
  panelAlt: "#171C27",
  line: "#232A38",
  text: "#E7EBF3",
  textDim: "#8B93A7",
  critical: "#FF5C5C",
  warn: "#F2B84B",
  safe: "#2BD4A0",
  signal: "#5B7CFA",
};

const SECTORS = [
  { id: "ecommerce", label: "E-Commerce", icon: ShoppingCart },
  { id: "shopping", label: "Shopping App", icon: Smartphone },
  { id: "ott", label: "OTT Platform", icon: Tv },
];

const FIRST = ["Aarav","Meera","Rohan","Isha","Kabir","Ananya","Vikram","Priya","Dev","Sana","Nikhil","Tara","Yusuf","Diya","Arjun","Neha","Karan","Riya","Sameer","Pooja"];
const LAST = ["Sharma","Verma","Iyer","Khan","Reddy","Nair","Kapoor","Gupta","Joshi","Bhatt","Rao","Singh","Menon","Chatterjee","Desai"];

function seededRandom(seed) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function genCustomers(sector, n = 42) {
  const rand = seededRandom(sector.charCodeAt(0) * 97 + 13);
  const customers = [];
  for (let i = 0; i < n; i++) {
    const risk = Math.round(rand() * 100);
    const name = `${FIRST[Math.floor(rand() * FIRST.length)]} ${LAST[Math.floor(rand() * LAST.length)]}`;
    let metrics = {};
    let reasons = [];
    let suggestions = [];

    if (sector === "ecommerce") {
      metrics = {
        "Cart abandonment rate": `${Math.round(30 + risk * 0.6)}%`,
        "Days since last purchase": Math.round(5 + risk * 0.9),
        "Avg order value trend": risk > 50 ? "↓ 18%" : "↑ 6%",
      };
      if (risk > 70) reasons = ["Cart abandonment rate rose sharply over 3 sessions", "No purchase in 45+ days after being a weekly buyer", "Stopped opening promotional emails"];
      else if (risk > 40) reasons = ["Order frequency down from monthly to quarterly", "Browsed competitor-linked category pages before drop-off"];
      else reasons = ["Consistent purchase cadence", "Redeemed last two loyalty offers"];
      suggestions = risk > 70
        ? ["Send a personalized win-back discount (15–20%)", "Trigger cart-recovery email within 2 hours of abandonment", "Offer free shipping on next order"]
        : risk > 40
        ? ["Nudge with a curated restock reminder", "A/B test a loyalty-points bonus"]
        : ["Continue current engagement cadence", "Invite to referral program"];
    } else if (sector === "shopping") {
      metrics = {
        "Session frequency (7d)": Math.max(1, Math.round(12 - risk * 0.1)),
        "App opens trend": risk > 50 ? "↓ 32%" : "→ stable",
        "Wishlist activity": risk > 50 ? "Dormant" : "Active",
      };
      if (risk > 70) reasons = ["App opens dropped from daily to under twice a week", "Uninstalled and reinstalled once in last 30 days", "Push notification opt-out detected"];
      else if (risk > 40) reasons = ["Wishlist items untouched for 20+ days", "Shorter session durations vs. 30-day average"];
      else reasons = ["Regular browsing sessions maintained", "Engaging with new arrivals section"];
      suggestions = risk > 70
        ? ["Re-permission push notifications with a value prompt", "Send a 'we miss you' in-app banner with a limited offer", "Simplify checkout — flag friction in last session"]
        : risk > 40
        ? ["Surface wishlist items with a price-drop alert", "Gamify next visit with a spin-the-wheel offer"]
        : ["Maintain personalized recommendations", "Early access to new drops"];
    } else {
      metrics = {
        "Watch-time decay": `${Math.round(risk * 0.8)}%`,
        "Days since last watch": Math.round(2 + risk * 0.7),
        "Genres explored (30d)": Math.max(1, Math.round(6 - risk * 0.05)),
      };
      if (risk > 70) reasons = ["Watch time dropped over 70% vs. prior month", "Abandoned an in-progress series mid-season", "Payment method flagged as expiring"];
      else if (risk > 40) reasons = ["Watching frequency reduced to once a week", "No new genre exploration in 3 weeks"];
      else reasons = ["Actively completing multiple series", "Rated content — high engagement signal"];
      suggestions = risk > 70
        ? ["Prompt to resume the abandoned series with a recap", "Offer a discounted plan tier before renewal", "Update payment method reminder"]
        : risk > 40
        ? ["Recommend trending titles in previously watched genres", "Highlight a limited-time exclusive premiere"]
        : ["Continue tailored recommendations", "Invite to early-access previews"];
    }

    customers.push({
      id: `${sector.slice(0, 2).toUpperCase()}-${1000 + i}`,
      name,
      risk,
      band: risk > 70 ? "High" : risk > 40 ? "Medium" : "Low",
      metrics,
      reasons,
      suggestions,
      lastActive: `${Math.round(1 + risk * 0.3)}d ago`,
    });
  }
  return customers.sort((a, b) => b.risk - a.risk);
}

function trendFor(sector) {
  const base = sector === "ott" ? 8 : sector === "ecommerce" ? 6 : 7;
  return Array.from({ length: 8 }, (_, i) => ({
    week: `W${i + 1}`,
    churn: Math.round((base + Math.sin(i / 1.4) * 2 + i * 0.35) * 10) / 10,
  }));
}

function riskDistribution(customers) {
  const bands = { Low: 0, Medium: 0, High: 0 };
  customers.forEach((c) => (bands[c.band] += 1));
  return [
    { name: "Low", value: bands.Low, color: COLORS.safe },
    { name: "Medium", value: bands.Medium, color: COLORS.warn },
    { name: "High", value: bands.High, color: COLORS.critical },
  ];
}

/* ---------------------------------------------------------------
   PULSE GAUGE — signature element.
   An ECG-style line whose amplitude flattens as risk rises.
----------------------------------------------------------------*/
function PulseGauge({ risk }) {
  const amp = Math.max(4, 26 - risk * 0.22); // higher risk -> flatter line
  const color = risk > 70 ? COLORS.critical : risk > 40 ? COLORS.warn : COLORS.safe;
  const points = useMemo(() => {
    const w = 240, h = 60, mid = h / 2;
    const pts = [];
    for (let x = 0; x <= w; x += 4) {
      const t = x / w;
      const spike = Math.exp(-Math.pow((t * 6) % 6 - 3, 2) * 6) * amp;
      pts.push(`${x},${mid - spike + (Math.random() - 0.5) * 1.2}`);
    }
    return pts.join(" ");
  }, [amp]);

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <svg viewBox="0 0 240 60" width="100%" height="70" style={{ maxWidth: 260 }}>
        <polyline points={points} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" opacity="0.9" />
      </svg>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
        <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 34, fontWeight: 600, color }}>{risk}</span>
        <span style={{ color: COLORS.textDim, fontSize: 13 }}>/ 100 churn probability</span>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------
   SHARED UI PIECES
----------------------------------------------------------------*/
function Panel({ children, style }) {
  return (
    <div style={{ background: COLORS.panel, border: `1px solid ${COLORS.line}`, borderRadius: 10, padding: 20, ...style }}>
      {children}
    </div>
  );
}

function Badge({ band }) {
  const color = band === "High" ? COLORS.critical : band === "Medium" ? COLORS.warn : COLORS.safe;
  return (
    <span style={{
      color, border: `1px solid ${color}55`, background: `${color}18`,
      padding: "2px 9px", borderRadius: 20, fontSize: 12, fontWeight: 600, letterSpacing: 0.2,
    }}>
      {band}
    </span>
  );
}

/* ---------------------------------------------------------------
   SCREENS
----------------------------------------------------------------*/
function Landing({ onRegister }) {
  const [company, setCompany] = useState("");
  const [sector, setSector] = useState("ecommerce");

  return (
    <div style={{ minHeight: "100vh", background: COLORS.ink, color: COLORS.text, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ width: 420 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
          <Activity size={22} color={COLORS.signal} />
          <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 20, fontWeight: 600 }}>Vitals</span>
          <span style={{ color: COLORS.textDim, fontSize: 13 }}>— churn intelligence</span>
        </div>
        <Panel>
          <h1 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 22, margin: "0 0 6px" }}>Register your company</h1>
          <p style={{ color: COLORS.textDim, fontSize: 13, margin: "0 0 20px" }}>See who's about to leave — before they do.</p>

          <label style={{ fontSize: 12, color: COLORS.textDim }}>Company name</label>
          <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Northstar Retail"
            style={{ width: "100%", boxSizing: "border-box", background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, padding: "10px 12px", color: COLORS.text, margin: "6px 0 18px", fontSize: 14 }} />

          <label style={{ fontSize: 12, color: COLORS.textDim }}>Sector</label>
          <div style={{ display: "flex", gap: 8, margin: "6px 0 22px" }}>
            {SECTORS.map((s) => {
              const Icon = s.icon;
              const active = sector === s.id;
              return (
                <button key={s.id} onClick={() => setSector(s.id)}
                  style={{
                    flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
                    padding: "12px 8px", borderRadius: 8, cursor: "pointer",
                    background: active ? `${COLORS.signal}22` : COLORS.panelAlt,
                    border: `1px solid ${active ? COLORS.signal : COLORS.line}`,
                    color: active ? COLORS.text : COLORS.textDim,
                  }}>
                  <Icon size={16} />
                  <span style={{ fontSize: 11 }}>{s.label}</span>
                </button>
              );
            })}
          </div>

          <button onClick={() => company.trim() && onRegister(company.trim(), sector)}
            style={{
              width: "100%", padding: "11px 0", borderRadius: 8, border: "none", cursor: "pointer",
              background: COLORS.signal, color: "#fff", fontWeight: 600, fontSize: 14,
            }}>
            Create account & continue
          </button>
        </Panel>
        <p style={{ textAlign: "center", color: COLORS.textDim, fontSize: 12, marginTop: 16 }}>Demo build — registration and login are simulated.</p>
      </div>
    </div>
  );
}

function Login({ companyName, onLogin, onBack }) {
  const [loading, setLoading] = useState(false);
  return (
    <div style={{ minHeight: "100vh", background: COLORS.ink, color: COLORS.text, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ width: 380 }}>
        <button onClick={onBack} style={{ background: "none", border: "none", color: COLORS.textDim, display: "flex", alignItems: "center", gap: 6, cursor: "pointer", marginBottom: 20, fontSize: 13 }}>
          <ArrowLeft size={14} /> Back
        </button>
        <Panel>
          <h1 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 22, margin: "0 0 6px" }}>Secure login</h1>
          <p style={{ color: COLORS.textDim, fontSize: 13, margin: "0 0 20px" }}>{companyName} · authenticating via token server</p>
          <label style={{ fontSize: 12, color: COLORS.textDim }}>Work email</label>
          <input defaultValue="admin@company.com" style={{ width: "100%", boxSizing: "border-box", background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, padding: "10px 12px", color: COLORS.text, margin: "6px 0 14px", fontSize: 14 }} />
          <label style={{ fontSize: 12, color: COLORS.textDim }}>Password</label>
          <input type="password" defaultValue="••••••••" style={{ width: "100%", boxSizing: "border-box", background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, padding: "10px 12px", color: COLORS.text, margin: "6px 0 22px", fontSize: 14 }} />
          <button onClick={() => { setLoading(true); setTimeout(onLogin, 700); }}
            style={{ width: "100%", padding: "11px 0", borderRadius: 8, border: "none", cursor: "pointer", background: COLORS.signal, color: "#fff", fontWeight: 600, fontSize: 14 }}>
            {loading ? "Verifying with auth server…" : "Log in"}
          </button>
        </Panel>
      </div>
    </div>
  );
}

function Sidebar({ tab, setTab, companyName, sector, onLogout }) {
  const items = [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "customers", label: "Customer List", icon: Users },
    { id: "reports", label: "Reports", icon: FileText },
  ];
  const SectorIcon = SECTORS.find((s) => s.id === sector)?.icon || Building2;
  return (
    <div style={{ width: 220, background: COLORS.panel, borderRight: `1px solid ${COLORS.line}`, display: "flex", flexDirection: "column", padding: "20px 14px", boxSizing: "border-box" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 8px 20px" }}>
        <Activity size={20} color={COLORS.signal} />
        <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 16, color: COLORS.text }}>Vitals</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px 20px", borderBottom: `1px solid ${COLORS.line}`, marginBottom: 14 }}>
        <SectorIcon size={16} color={COLORS.textDim} />
        <div>
          <div style={{ fontSize: 13, color: COLORS.text, fontWeight: 500 }}>{companyName}</div>
          <div style={{ fontSize: 11, color: COLORS.textDim }}>{SECTORS.find((s) => s.id === sector)?.label}</div>
        </div>
      </div>
      {items.map((it) => {
        const Icon = it.icon;
        const active = tab === it.id;
        return (
          <button key={it.id} onClick={() => setTab(it.id)}
            style={{
              display: "flex", alignItems: "center", gap: 10, padding: "10px 10px", borderRadius: 8, marginBottom: 4,
              background: active ? `${COLORS.signal}1f` : "transparent", border: "none", cursor: "pointer",
              color: active ? COLORS.text : COLORS.textDim, fontSize: 13.5, textAlign: "left",
            }}>
            <Icon size={16} /> {it.label}
          </button>
        );
      })}
      <div style={{ flex: 1 }} />
      <button onClick={onLogout} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 10px", borderRadius: 8, background: "transparent", border: "none", cursor: "pointer", color: COLORS.textDim, fontSize: 13.5 }}>
        <LogOut size={16} /> Log out
      </button>
    </div>
  );
}

function StatCard({ label, value, sub, accent }) {
  return (
    <Panel style={{ flex: 1 }}>
      <div style={{ fontSize: 12, color: COLORS.textDim, marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 26, fontWeight: 600, color: accent || COLORS.text }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: COLORS.textDim, marginTop: 4 }}>{sub}</div>}
    </Panel>
  );
}

function Overview({ customers, sector }) {
  const trend = trendFor(sector);
  const dist = riskDistribution(customers);
  const avgRisk = Math.round(customers.reduce((a, c) => a + c.risk, 0) / customers.length);
  const highRisk = customers.filter((c) => c.band === "High").length;

  return (
    <div>
      <h2 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 20, margin: "0 0 4px", color: COLORS.text }}>Overall dashboard</h2>
      <p style={{ color: COLORS.textDim, fontSize: 13, margin: "0 0 20px" }}>Live churn signal across your entire customer base.</p>

      <div style={{ display: "flex", gap: 14, marginBottom: 18 }}>
        <StatCard label="Customers monitored" value={customers.length} />
        <StatCard label="Average churn probability" value={`${avgRisk}%`} accent={avgRisk > 55 ? COLORS.critical : COLORS.warn} />
        <StatCard label="High-risk customers" value={highRisk} sub="need attention this week" accent={COLORS.critical} />
        <StatCard label="Predicted retained" value={customers.length - highRisk} accent={COLORS.safe} />
      </div>

      <div style={{ display: "flex", gap: 14 }}>
        <Panel style={{ flex: 2 }}>
          <div style={{ fontSize: 13, color: COLORS.textDim, marginBottom: 10 }}>Churn rate trend (8 weeks)</div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="churnGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={COLORS.signal} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={COLORS.signal} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={COLORS.line} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="week" stroke={COLORS.textDim} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis stroke={COLORS.textDim} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} unit="%" />
              <Tooltip contentStyle={{ background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, fontSize: 12 }} />
              <Area type="monotone" dataKey="churn" stroke={COLORS.signal} fill="url(#churnGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>
        <Panel style={{ flex: 1 }}>
          <div style={{ fontSize: 13, color: COLORS.textDim, marginBottom: 10 }}>Risk distribution</div>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={dist} dataKey="value" nameKey="name" innerRadius={50} outerRadius={78} paddingAngle={3}>
                {dist.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip contentStyle={{ background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", justifyContent: "space-around", marginTop: 8 }}>
            {dist.map((d) => (
              <div key={d.name} style={{ textAlign: "center" }}>
                <div style={{ width: 8, height: 8, borderRadius: 8, background: d.color, margin: "0 auto 4px" }} />
                <div style={{ fontSize: 11, color: COLORS.textDim }}>{d.name}: {d.value}</div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function CustomerList({ customers, onSelect }) {
  const [query, setQuery] = useState("");
  const filtered = customers.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()) || c.id.toLowerCase().includes(query.toLowerCase()));

  return (
    <div>
      <h2 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 20, margin: "0 0 14px", color: COLORS.text }}>Customer list</h2>
      <div style={{ position: "relative", marginBottom: 16, maxWidth: 340 }}>
        <Search size={15} color={COLORS.textDim} style={{ position: "absolute", left: 12, top: 11 }} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search customer by name or ID"
          style={{ width: "100%", boxSizing: "border-box", background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, padding: "9px 12px 9px 34px", color: COLORS.text, fontSize: 13.5 }} />
      </div>
      <Panel style={{ padding: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 0.8fr 0.8fr 0.4fr", padding: "12px 18px", borderBottom: `1px solid ${COLORS.line}`, color: COLORS.textDim, fontSize: 11.5, textTransform: "uppercase", letterSpacing: 0.5 }}>
          <span>Customer</span><span>ID</span><span>Last active</span><span>Risk</span><span></span>
        </div>
        {filtered.map((c) => (
          <div key={c.id} onClick={() => onSelect(c)}
            style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 0.8fr 0.8fr 0.4fr", padding: "13px 18px", borderBottom: `1px solid ${COLORS.line}`, alignItems: "center", cursor: "pointer", fontSize: 13.5, color: COLORS.text }}>
            <span>{c.name}</span>
            <span style={{ color: COLORS.textDim, fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>{c.id}</span>
            <span style={{ color: COLORS.textDim }}>{c.lastActive}</span>
            <span><Badge band={c.band} /></span>
            <ChevronRight size={15} color={COLORS.textDim} />
          </div>
        ))}
        {filtered.length === 0 && <div style={{ padding: 24, color: COLORS.textDim, fontSize: 13 }}>No customers match "{query}".</div>}
      </Panel>
    </div>
  );
}

function CustomerDetail({ customer, onClose }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "#00000090", display: "flex", justifyContent: "flex-end", zIndex: 50 }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 460, background: COLORS.panel, height: "100%", overflowY: "auto", padding: 28, boxSizing: "border-box", borderLeft: `1px solid ${COLORS.line}` }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 20 }}>
          <div>
            <h2 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 19, margin: 0, color: COLORS.text }}>{customer.name}</h2>
            <span style={{ color: COLORS.textDim, fontSize: 12, fontFamily: "'IBM Plex Mono', monospace" }}>{customer.id}</span>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: COLORS.textDim }}><X size={20} /></button>
        </div>

        <Panel style={{ marginBottom: 16, display: "flex", justifyContent: "center" }}>
          <PulseGauge risk={customer.risk} />
        </Panel>

        <div style={{ fontSize: 12, color: COLORS.textDim, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>Behavioral signals</div>
        <Panel style={{ marginBottom: 16 }}>
          {Object.entries(customer.metrics).map(([k, v]) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13.5, borderBottom: `1px solid ${COLORS.line}` }}>
              <span style={{ color: COLORS.textDim }}>{k}</span>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace" }}>{v}</span>
            </div>
          ))}
        </Panel>

        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: COLORS.textDim, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
          <AlertTriangle size={13} /> Why this customer might leave
        </div>
        <Panel style={{ marginBottom: 16 }}>
          {customer.reasons.map((r, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 13.5, padding: "6px 0", color: COLORS.text }}>
              <TrendingDown size={14} color={COLORS.critical} style={{ flexShrink: 0, marginTop: 2 }} />
              {r}
            </div>
          ))}
        </Panel>

        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: COLORS.textDim, marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
          <Sparkles size={13} /> AI-suggested retention actions
        </div>
        <Panel>
          {customer.suggestions.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 8, fontSize: 13.5, padding: "6px 0", color: COLORS.text }}>
              <ShieldCheck size={14} color={COLORS.safe} style={{ flexShrink: 0, marginTop: 2 }} />
              {s}
            </div>
          ))}
        </Panel>
      </div>
    </div>
  );
}

function Reports({ customers, companyName }) {
  const avgRisk = Math.round(customers.reduce((a, c) => a + c.risk, 0) / customers.length);
  const highRisk = customers.filter((c) => c.band === "High").length;
  const bySector = riskDistribution(customers);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h2 style={{ fontFamily: "'Space Grotesk', sans-serif", fontSize: 20, margin: 0, color: COLORS.text }}>Reports</h2>
        <button style={{ display: "flex", alignItems: "center", gap: 6, background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, padding: "8px 14px", color: COLORS.text, fontSize: 13, cursor: "pointer" }}>
          <Download size={14} /> Export summary (.csv)
        </button>
      </div>
      <Panel style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: COLORS.textDim, marginBottom: 10 }}>Weekly churn summary — {companyName}</div>
        <p style={{ fontSize: 13.5, lineHeight: 1.6, color: COLORS.text, margin: 0 }}>
          Of {customers.length} customers monitored, {highRisk} are flagged high-risk with an average churn
          probability of {avgRisk}%. The most common driver this week is declining engagement frequency,
          followed by drop-off in transactional or watch activity. Suggested retention actions have been
          generated for all high and medium-risk accounts.
        </p>
      </Panel>
      <Panel>
        <div style={{ fontSize: 13, color: COLORS.textDim, marginBottom: 10 }}>Risk band breakdown</div>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={bySector}>
            <CartesianGrid stroke={COLORS.line} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" stroke={COLORS.textDim} tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis stroke={COLORS.textDim} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ background: COLORS.panelAlt, border: `1px solid ${COLORS.line}`, borderRadius: 8, fontSize: 12 }} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {bySector.map((d, i) => <Cell key={i} fill={d.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Panel>
    </div>
  );
}

/* ---------------------------------------------------------------
   ROOT APP
----------------------------------------------------------------*/
export default function App() {
  const [screen, setScreen] = useState("landing"); // landing | login | dashboard
  const [company, setCompany] = useState({ name: "", sector: "ecommerce" });
  const [tab, setTab] = useState("overview");
  const [customers, setCustomers] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    if (screen === "dashboard") setCustomers(genCustomers(company.sector));
  }, [screen, company.sector]);

  const fontLink = (
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet" />
  );

  if (screen === "landing") {
    return <>{fontLink}<Landing onRegister={(name, sector) => { setCompany({ name, sector }); setScreen("login"); }} /></>;
  }
  if (screen === "login") {
    return <>{fontLink}<Login companyName={company.name} onBack={() => setScreen("landing")} onLogin={() => setScreen("dashboard")} /></>;
  }

  return (
    <>
      {fontLink}
      <div style={{ display: "flex", minHeight: "100vh", background: COLORS.ink, fontFamily: "'Inter', sans-serif" }}>
        <Sidebar tab={tab} setTab={setTab} companyName={company.name} sector={company.sector} onLogout={() => setScreen("landing")} />
        <div style={{ flex: 1, padding: 28, overflowY: "auto" }}>
          {tab === "overview" && <Overview customers={customers} sector={company.sector} />}
          {tab === "customers" && <CustomerList customers={customers} onSelect={setSelected} />}
          {tab === "reports" && <Reports customers={customers} companyName={company.name} />}
        </div>
      </div>
      {selected && <CustomerDetail customer={selected} onClose={() => setSelected(null)} />}
    </>
  );
}
