import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Device, Call } from "@twilio/voice-sdk";
import "./style.css";

const API = import.meta.env.VITE_PHONE_API ?? "http://localhost:8080";

function App() {
  const [number, setNumber] = useState("");
  const [identity, setIdentity] = useState("user");
  const [status, setStatus] = useState("initializing");
  const [muted, setMuted] = useState(false);
  const device = useRef<Device | null>(null);
  const call = useRef<Call | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const response = await fetch(`${API}/token?identity=${encodeURIComponent(identity)}`);
      if (!response.ok) throw new Error("token request failed");
      const data = await response.json();
      if (!active) return;
      const d = new Device(data.token, { codecPreferences: ["opus", "pcmu"] });
      d.on("registered", () => setStatus("ready"));
      d.on("error", (error) => setStatus(`error: ${error.message}`));
      await d.register();
      device.current = d;
    })().catch((error) => setStatus(`error: ${error.message}`));
    return () => {
      active = false;
      device.current?.destroy();
      device.current = null;
    };
  }, [identity]);

  const dial = async () => {
    if (!/^\+[1-9]\d{7,14}$/.test(number)) {
      setStatus("enter an E.164 number, e.g. +15551234567");
      return;
    }
    if (!device.current) return;
    setStatus("calling");
    const c = await device.current.connect({ params: { To: number } });
    call.current = c;
    c.on("accept", () => setStatus("connected"));
    c.on("disconnect", () => { call.current = null; setMuted(false); setStatus("ready"); });
    c.on("cancel", () => setStatus("ready"));
    c.on("reject", () => setStatus("rejected"));
    c.on("error", (error) => setStatus(`error: ${error.message}`));
  };

  const hangup = () => call.current?.disconnect();
  const toggleMute = () => {
    if (!call.current) return;
    const next = !muted;
    call.current.mute(next);
    setMuted(next);
  };

  return <main className="phone">
    <header><strong>TinyD Phone</strong><span>{status}</span></header>
    <label className="identity">Identity<input value={identity} onChange={(e) => setIdentity(e.target.value)} disabled={!!call.current} /></label>
    <input className="number" inputMode="tel" autoComplete="tel" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="+1 555 123 4567" aria-label="Phone number" />
    <section className="actions">
      <button onClick={toggleMute} disabled={!call.current}>{muted ? "Unmute" : "Mute"}</button>
      <button className="call" onClick={dial} disabled={status === "calling" || status === "connected"}>Call</button>
      <button className="hangup" onClick={hangup} disabled={!call.current}>End</button>
    </section>
    <p className="notice">Calls use encrypted WebRTC media between this client and the voice provider. Never place secrets in browser code.</p>
  </main>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
