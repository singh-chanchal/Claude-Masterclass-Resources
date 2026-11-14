import { useState } from "react";
import { api } from "../api.js";
import { Alert, Modal, Spinner } from "./ui.jsx";

// Same length rule as signup (backend enforces it too: 8–72 characters).
const MIN = 8, MAX = 72;

export default function ChangePasswordModal({ onClose, onDone }) {
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function save(e) {
    e.preventDefault();
    if (form.next.length < MIN || form.next.length > MAX) return setError(`New password must be ${MIN}–${MAX} characters.`);
    if (form.next !== form.confirm) return setError("New passwords don't match.");
    setBusy(true); setError("");
    try {
      await api("/api/auth/change-password", {
        method: "POST",
        body: { current_password: form.current, new_password: form.next },
      });
      onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Change password" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>Current password
          <input type="password" required autoFocus autoComplete="current-password" value={form.current} onChange={set("current")} />
        </label>
        <label>New password
          <input type="password" required minLength={MIN} maxLength={MAX} autoComplete="new-password" value={form.next} onChange={set("next")} />
        </label>
        <label>Confirm new password
          <input type="password" required autoComplete="new-password" value={form.confirm} onChange={set("confirm")} />
        </label>
        <Alert>{error}</Alert>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy}>{busy ? <Spinner label="Saving…" /> : "Save"}</button>
        </div>
      </form>
    </Modal>
  );
}
