"""Tema visual do Zek Download (CSS do GTK 3)."""

CSS = b"""
window.fx-window { background-color: #0e1117; }
headerbar.fx-header { background-image: none; background-color: #0b0e13; border-bottom: 1px solid #1c222d;
  box-shadow: none; color: #e8ecf3; min-height: 44px; }
headerbar.fx-header .title { color: #e8ecf3; font-weight: 700; }
headerbar.fx-header button { background-image: none; background-color: transparent; border: none;
  box-shadow: none; color: #aab3c5; }
headerbar.fx-header button:hover { background-color: #1c222d; color: #ffffff; }

.fx-card { background-color: #161b24; border: 1px solid #232a36; border-radius: 16px; }
.fx-h1 { color: #ffffff; font-size: 17px; font-weight: 700; }
.fx-h2 { color: #e8ecf3; font-size: 14px; font-weight: 700; }
.fx-text { color: #c7cfdd; }
.fx-dim { color: #8b95a7; font-size: 12px; }
.fx-hint { color: #8b95a7; font-size: 12px; }

entry.fx-entry { background-image: none; background-color: #0e1117; color: #e8ecf3; caret-color: #22d3ee;
  border: 1px solid #2a3342; border-radius: 10px; padding: 10px 14px; min-height: 22px; box-shadow: none; }
entry.fx-entry:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.30); }
entry.fx-entry selection { background-color: #6366f1; color: #ffffff; }

button.fx-primary { background-image: linear-gradient(135deg, #6366f1, #22b8e0); color: #ffffff; border: none;
  border-radius: 10px; padding: 10px 24px; font-weight: 700; text-shadow: none; box-shadow: none; }
button.fx-primary:hover { background-image: linear-gradient(135deg, #7c7ff5, #3fd0f0); }
button.fx-primary:active { background-image: linear-gradient(135deg, #5154d8, #1a9cc2); }
button.fx-primary:disabled { opacity: 0.5; }

button.fx-secondary { background-image: none; background-color: #1d2430; color: #dbe1ec; border: 1px solid #2a3342;
  border-radius: 10px; padding: 10px 16px; text-shadow: none; box-shadow: none; }
button.fx-secondary:hover { background-color: #263040; }

button.fx-seg { background-image: none; background-color: #0e1117; color: #8b95a7; border: 1px solid #2a3342;
  padding: 8px 20px; box-shadow: none; text-shadow: none; font-weight: 600; }
button.fx-seg:hover { color: #ffffff; }
button.fx-seg:checked { background-color: #6366f1; border-color: #6366f1; color: #ffffff; }
button.fx-seg-left { border-radius: 10px 0 0 10px; }
button.fx-seg-right { border-radius: 0 10px 10px 0; border-left-width: 0; }

combobox.fx-combo button { background-image: none; background-color: #0e1117; color: #e8ecf3;
  border: 1px solid #2a3342; border-radius: 10px; padding: 8px 12px; box-shadow: none; text-shadow: none; }
combobox.fx-combo button:hover { border-color: #6366f1; }
combobox.fx-combo arrow { color: #8b95a7; }
filechooser button.fx-file, button.fx-file { background-image: none; background-color: #0e1117; color: #e8ecf3;
  border: 1px solid #2a3342; border-radius: 10px; padding: 8px 12px; box-shadow: none; text-shadow: none; }
button.fx-file:hover { border-color: #6366f1; }
checkbutton.fx-check label { color: #c7cfdd; }

.fx-banner { background-image: linear-gradient(90deg, rgba(99,102,241,0.22), rgba(34,184,224,0.16));
  border: 1px solid rgba(99,102,241,0.45); border-radius: 12px; }
.fx-banner label { color: #e8ecf3; font-weight: 600; }

list.fx-list { background-color: transparent; }
row.fx-row { background-color: #161b24; border: 1px solid #232a36; border-radius: 14px; margin: 5px 0; padding: 0; }
row.fx-row:hover { background-color: #1a202b; }
row.fx-row.fx-done { border-color: rgba(52,211,153,0.45); }
row.fx-row.fx-error { border-color: rgba(248,113,113,0.55); }
.fx-row-title { color: #ffffff; font-weight: 700; font-size: 14px; }
.fx-row-status { color: #9aa5b8; font-size: 12px; }
row.fx-done .fx-row-status { color: #34d399; }
row.fx-error .fx-row-status { color: #f87171; }
.fx-icon-badge { background-color: #232a3a; border-radius: 12px; color: #9aa7ff; }

progressbar.fx-progress trough { background-color: #0e1117; border: none; border-radius: 99px; min-height: 8px; }
progressbar.fx-progress progress { background-image: linear-gradient(90deg, #6366f1, #22d3ee); border: none;
  border-radius: 99px; min-height: 8px; }
row.fx-done progressbar.fx-progress progress { background-image: linear-gradient(90deg, #10b981, #34d399); }
row.fx-error progressbar.fx-progress progress { background-image: linear-gradient(90deg, #ef4444, #f87171); }

button.fx-icon { background-image: none; background-color: transparent; border: none; box-shadow: none;
  color: #8b95a7; padding: 6px; border-radius: 8px; min-width: 0; min-height: 0; }
button.fx-icon:hover { background-color: #263040; color: #ffffff; }

.fx-step-num { background-image: linear-gradient(135deg, #6366f1, #22b8e0); color: #ffffff; font-weight: 800;
  border-radius: 99px; min-width: 34px; min-height: 34px; }
.fx-step-card { background-color: #161b24; border: 1px solid #232a36; border-radius: 14px; }

.fx-footer { background-color: #0b0e13; border-top: 1px solid #1c222d; }
.fx-footer label { color: #8b95a7; font-size: 12px; }
.fx-dot-ok { color: #34d399; }
.fx-dot-busy { color: #fbbf24; }
.fx-dot-err { color: #f87171; }
"""
