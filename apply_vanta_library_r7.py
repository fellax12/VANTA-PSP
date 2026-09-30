#!/usr/bin/env python3
"""VANTA PSP UI R7

Adds controller-first launcher navigation and persistent manual game covers.
Designed to run AFTER the stable VANTA layer and Memory Scanner R2 patches.
It intentionally does not touch PPSSPP core, CwCheatScreen.cpp, memory scanning,
or cheat logic.
"""
from pathlib import Path
import re
import sys

MARKER = "VANTA_LIBRARY_UI_R7"


def class_body_open(src: str, class_name: str) -> int:
    m = re.search(r"\bclass\s+" + re.escape(class_name) + r"\b[^\{]*\{", src)
    if not m:
        raise RuntimeError(f"class {class_name} not found")
    return src.find("{", m.start())


def matching_brace(src: str, open_pos: int) -> int:
    if src[open_pos] != "{":
        raise ValueError("open_pos is not a brace")
    depth = 0
    i = open_pos
    state = "code"
    while i < len(src):
        ch = src[i]
        nx = src[i + 1] if i + 1 < len(src) else ""
        if state == "code":
            if ch == '"':
                state = "string"
            elif ch == "'":
                state = "char"
            elif ch == "/" and nx == "/":
                state = "line"
                i += 1
            elif ch == "/" and nx == "*":
                state = "block"
                i += 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        elif state == "string":
            if ch == "\\":
                i += 1
            elif ch == '"':
                state = "code"
        elif state == "char":
            if ch == "\\":
                i += 1
            elif ch == "'":
                state = "code"
        elif state == "line":
            if ch == "\n":
                state = "code"
        elif state == "block":
            if ch == "*" and nx == "/":
                state = "code"
                i += 1
        i += 1
    raise RuntimeError("unmatched brace")


def find_method(src: str, name: str):
    # Method declaration at line start. We deliberately avoid invocations/lambdas.
    pat = re.compile(
        r"(?m)^[ \t]*(?:@Override[ \t]*(?:\r?\n[ \t]*)?)?"
        r"(?:(?:public|private|protected|static|final|synchronized|native|abstract)\s+)*"
        r"[\w.$<>\[\], ?]+\s+" + re.escape(name) + r"\s*\([^;{}]*\)\s*(?:throws\s+[^\{]+)?\{"
    )
    m = pat.search(src)
    if not m:
        raise RuntimeError(f"method {name} not found")
    open_pos = src.find("{", m.start(), m.end())
    close_pos = matching_brace(src, open_pos)
    return m.start(), open_pos, close_pos, src[m.start():open_pos]


def inject_method_start(src: str, name: str, code: str) -> str:
    _, op, _, _ = find_method(src, name)
    return src[:op + 1] + "\n" + code.rstrip() + "\n" + src[op + 1:]


def inject_method_end(src: str, name: str, code: str) -> str:
    _, _, cl, _ = find_method(src, name)
    return src[:cl] + "\n" + code.rstrip() + "\n" + src[cl:]


def patch_game_tile_return(src: str) -> str:
    start, op, cl, decl = find_method(src, "gameTile")
    # Extract parameter variable names from the source declaration.
    paren0 = decl.find("(")
    paren1 = decl.rfind(")")
    params = decl[paren0 + 1:paren1].strip()
    parts = [p.strip() for p in params.split(",") if p.strip()]
    if len(parts) < 2:
        raise RuntimeError("gameTile parameters not recognized")
    game_var = re.findall(r"[A-Za-z_$][\w$]*", parts[0])[-1]
    bool_var = re.findall(r"[A-Za-z_$][\w$]*", parts[1])[-1]

    body = src[op + 1:cl]
    returns = list(re.finditer(r"(?m)^(?P<indent>[ \t]*)return\s+(?P<expr>[^;\n]+);\s*$", body))
    if not returns:
        raise RuntimeError("gameTile final return not found")
    last = returns[-1]
    expr = last.group("expr").strip()
    if expr in ("true", "false", "null"):
        raise RuntimeError(f"unexpected final gameTile return: {expr}")
    replacement = (
        last.group("indent")
        + f"return vantaPrepareGameTile({expr}, {game_var}, {bool_var});"
    )
    body = body[:last.start()] + replacement + body[last.end():]
    return src[:op + 1] + body + src[cl:]


def append_before_class_end(src: str, class_name: str, code: str) -> str:
    op = class_body_open(src, class_name)
    cl = matching_brace(src, op)
    return src[:cl] + "\n\n" + code.rstrip() + "\n" + src[cl:]


ACTIVITY_FIELDS = r'''
    // VANTA_LIBRARY_UI_R7: launcher-only UI state. Core/cheat/scanner code is untouched.
    private static final int REQ_PICK_COVER = 9103;
    private static final String VANTA_GAME_TILE_TAG = "vanta_game_tile:";
    private String vantaCoverTargetGameUri = null;
    private long vantaLastAxisNavigationAt = 0L;
'''

ACTIVITY_HELPERS = r'''
    // ==================== VANTA_LIBRARY_UI_R7 ====================
    private android.view.View vantaPrepareGameTile(android.view.View raw,
                                                    final VantaPrefs.GameEntry game,
                                                    boolean compactTile) {
        if (raw == null || game == null) return raw;
        raw.setFocusable(true);
        raw.setFocusableInTouchMode(false);
        raw.setTag(VANTA_GAME_TILE_TAG + game.uri);
        raw.setContentDescription(game.name + ". Jogo PSP. Pressione A para abrir.");

        raw.setOnFocusChangeListener((view, focused) -> {
            view.animate()
                .scaleX(focused ? 1.035f : 1.0f)
                .scaleY(focused ? 1.035f : 1.0f)
                .setDuration(110L)
                .start();
            view.setAlpha(focused ? 1.0f : 0.94f);
            if (android.os.Build.VERSION.SDK_INT >= 21) {
                view.setElevation(focused ? dp(9) : dp(1));
            }
        });

        if (raw instanceof android.widget.LinearLayout) {
            android.widget.LinearLayout tile = (android.widget.LinearLayout) raw;
            android.widget.FrameLayout art = new android.widget.FrameLayout(this);
            int coverHeight = dp(compactTile ? 116 : 146);
            android.widget.LinearLayout.LayoutParams artLp =
                new android.widget.LinearLayout.LayoutParams(
                    android.view.ViewGroup.LayoutParams.MATCH_PARENT, coverHeight);
            artLp.bottomMargin = dp(10);

            android.widget.TextView placeholder = new android.widget.TextView(this);
            placeholder.setText("VANTA\nPSP");
            placeholder.setGravity(android.view.Gravity.CENTER);
            placeholder.setTextColor(TEXT);
            placeholder.setTextSize(compactTile ? 17f : 20f);
            placeholder.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
            placeholder.setLetterSpacing(0.10f);
            placeholder.setBackground(gradient(
                android.graphics.Color.rgb(20, 26, 42),
                android.graphics.Color.rgb(29, 39, 62),
                STROKE, dp(16), dp(1)));
            art.addView(placeholder, new android.widget.FrameLayout.LayoutParams(
                android.view.ViewGroup.LayoutParams.MATCH_PARENT,
                android.view.ViewGroup.LayoutParams.MATCH_PARENT));

            String coverUri = VantaPrefs.coverUri(this, game.uri);
            if (coverUri != null && !coverUri.isEmpty()) {
                try {
                    android.widget.ImageView cover = new android.widget.ImageView(this);
                    cover.setScaleType(android.widget.ImageView.ScaleType.CENTER_CROP);
                    cover.setImageURI(android.net.Uri.parse(coverUri));
                    art.addView(cover, new android.widget.FrameLayout.LayoutParams(
                        android.view.ViewGroup.LayoutParams.MATCH_PARENT,
                        android.view.ViewGroup.LayoutParams.MATCH_PARENT));
                } catch (Throwable ignored) {
                    // Keep the VANTA placeholder if the selected file disappeared.
                }
            }

            android.widget.TextView editCover = new android.widget.TextView(this);
            editCover.setText((coverUri == null || coverUri.isEmpty()) ? "＋ CAPA" : "✎ CAPA");
            editCover.setTextColor(TEXT);
            editCover.setTextSize(11f);
            editCover.setGravity(android.view.Gravity.CENTER);
            editCover.setPadding(dp(10), dp(5), dp(10), dp(5));
            editCover.setBackground(round(PANEL_2, dp(12), STROKE));
            editCover.setClickable(true);
            editCover.setFocusable(false);
            editCover.setOnClickListener(v -> vantaPickCover(game));
            android.widget.FrameLayout.LayoutParams editLp =
                new android.widget.FrameLayout.LayoutParams(
                    android.view.ViewGroup.LayoutParams.WRAP_CONTENT,
                    android.view.ViewGroup.LayoutParams.WRAP_CONTENT,
                    android.view.Gravity.END | android.view.Gravity.BOTTOM);
            editLp.setMargins(dp(8), dp(8), dp(8), dp(8));
            art.addView(editCover, editLp);

            tile.addView(art, 0, artLp);
        }
        return raw;
    }

    private void vantaPickCover(VantaPrefs.GameEntry game) {
        if (game == null) return;
        vantaCoverTargetGameUri = game.uri;
        android.content.Intent intent = new android.content.Intent(android.content.Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(android.content.Intent.CATEGORY_OPENABLE);
        intent.setType("image/*");
        intent.addFlags(android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION |
                        android.content.Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, REQ_PICK_COVER);
    }

    private android.view.View vantaGameTileAncestor(android.view.View view) {
        android.view.View current = view;
        while (current != null) {
            Object tag = current.getTag();
            if (tag instanceof String && ((String) tag).startsWith(VANTA_GAME_TILE_TAG)) {
                return current;
            }
            android.view.ViewParent parent = current.getParent();
            current = parent instanceof android.view.View ? (android.view.View) parent : null;
        }
        return null;
    }

    private void vantaCollectGameTiles(android.view.View root, java.util.List<android.view.View> out) {
        if (root == null) return;
        Object tag = root.getTag();
        if (tag instanceof String && ((String) tag).startsWith(VANTA_GAME_TILE_TAG)) {
            out.add(root);
            return;
        }
        if (root instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) root;
            for (int i = 0; i < group.getChildCount(); ++i) {
                vantaCollectGameTiles(group.getChildAt(i), out);
            }
        }
    }

    private boolean vantaControllerPage() {
        return currentPage == Page.LIBRARY || currentPage == Page.HOME;
    }

    private boolean vantaMoveControllerFocus(int direction) {
        if (!vantaControllerPage() || content == null) return false;
        java.util.ArrayList<android.view.View> tiles = new java.util.ArrayList<>();
        vantaCollectGameTiles(content, tiles);
        if (tiles.isEmpty()) return false;

        android.view.View focused = vantaGameTileAncestor(getCurrentFocus());
        if (focused == null) {
            android.view.View first = tiles.get(0);
            first.requestFocus();
            first.sendAccessibilityEvent(android.view.accessibility.AccessibilityEvent.TYPE_VIEW_FOCUSED);
            return true;
        }

        int index = tiles.indexOf(focused);
        if (index < 0) index = 0;
        int columns = currentPage == Page.LIBRARY ? Math.max(1, libraryColumns()) : Math.max(1, tiles.size());
        int target = index;
        if (direction == android.view.View.FOCUS_LEFT) target = index - 1;
        else if (direction == android.view.View.FOCUS_RIGHT) target = index + 1;
        else if (direction == android.view.View.FOCUS_UP && currentPage == Page.LIBRARY) target = index - columns;
        else if (direction == android.view.View.FOCUS_DOWN && currentPage == Page.LIBRARY) target = index + columns;
        else {
            android.view.View systemNext = focused.focusSearch(direction);
            if (systemNext != null) {
                systemNext.requestFocus();
                return true;
            }
            return false;
        }

        if (target >= 0 && target < tiles.size()) {
            android.view.View next = tiles.get(target);
            next.requestFocus();
            next.playSoundEffect(android.view.SoundEffectConstants.NAVIGATION_LEFT);
            return true;
        }

        android.view.View systemNext = focused.focusSearch(direction);
        if (systemNext != null) {
            systemNext.requestFocus();
            return true;
        }
        return false;
    }

    private boolean vantaHandleControllerKey(android.view.KeyEvent event) {
        if (!vantaControllerPage() || event.getAction() != android.view.KeyEvent.ACTION_DOWN) return false;
        int key = event.getKeyCode();
        if (key == android.view.KeyEvent.KEYCODE_DPAD_LEFT) return vantaMoveControllerFocus(android.view.View.FOCUS_LEFT);
        if (key == android.view.KeyEvent.KEYCODE_DPAD_RIGHT) return vantaMoveControllerFocus(android.view.View.FOCUS_RIGHT);
        if (key == android.view.KeyEvent.KEYCODE_DPAD_UP) return vantaMoveControllerFocus(android.view.View.FOCUS_UP);
        if (key == android.view.KeyEvent.KEYCODE_DPAD_DOWN) return vantaMoveControllerFocus(android.view.View.FOCUS_DOWN);

        if (key == android.view.KeyEvent.KEYCODE_BUTTON_A ||
            key == android.view.KeyEvent.KEYCODE_DPAD_CENTER ||
            key == android.view.KeyEvent.KEYCODE_ENTER) {
            android.view.View tile = vantaGameTileAncestor(getCurrentFocus());
            if (tile != null && tile.isClickable()) {
                tile.performClick();
                return true;
            }
        }
        return false;
    }

    private boolean vantaHandleAnalogNavigation(android.view.MotionEvent event) {
        if (!vantaControllerPage()) return false;
        int source = event.getSource();
        boolean joystick = (source & android.view.InputDevice.SOURCE_JOYSTICK) == android.view.InputDevice.SOURCE_JOYSTICK;
        boolean gamepad = (source & android.view.InputDevice.SOURCE_GAMEPAD) == android.view.InputDevice.SOURCE_GAMEPAD;
        if (!joystick && !gamepad) return false;

        float x = event.getAxisValue(android.view.MotionEvent.AXIS_HAT_X);
        float y = event.getAxisValue(android.view.MotionEvent.AXIS_HAT_Y);
        if (Math.abs(x) < 0.55f) x = event.getAxisValue(android.view.MotionEvent.AXIS_X);
        if (Math.abs(y) < 0.55f) y = event.getAxisValue(android.view.MotionEvent.AXIS_Y);
        if (Math.abs(x) < 0.68f && Math.abs(y) < 0.68f) return false;

        long now = android.os.SystemClock.uptimeMillis();
        if (now - vantaLastAxisNavigationAt < 170L) return true;
        vantaLastAxisNavigationAt = now;

        if (Math.abs(x) >= Math.abs(y)) {
            return vantaMoveControllerFocus(x < 0 ? android.view.View.FOCUS_LEFT : android.view.View.FOCUS_RIGHT);
        }
        return vantaMoveControllerFocus(y < 0 ? android.view.View.FOCUS_UP : android.view.View.FOCUS_DOWN);
    }

    private void vantaFocusFirstGameTileDeferred() {
        if (!vantaControllerPage() || content == null) return;
        content.post(() -> {
            android.view.View focused = getCurrentFocus();
            if (vantaGameTileAncestor(focused) != null) return;
            // Do not steal focus while the user is actively typing in library search.
            if (focused instanceof android.widget.EditText && focused.hasFocus()) return;
            java.util.ArrayList<android.view.View> tiles = new java.util.ArrayList<>();
            vantaCollectGameTiles(content, tiles);
            if (!tiles.isEmpty()) tiles.get(0).requestFocus();
        });
    }
    // ================== / VANTA_LIBRARY_UI_R7 ===================
'''

PREFS_HELPERS = r'''
    // VANTA_LIBRARY_UI_R7: manual covers are launcher metadata only.
    private static String coverKey(String gameUri) {
        String value = gameUri == null ? "" : gameUri;
        return "cover_" + Integer.toHexString(value.hashCode());
    }

    static String coverUri(android.content.Context context, String gameUri) {
        return p(context).getString(coverKey(gameUri), "");
    }

    static void setCoverUri(android.content.Context context, String gameUri, String coverUri) {
        p(context).edit().putString(coverKey(gameUri), coverUri == null ? "" : coverUri).apply();
    }
'''

DISPATCH_START = r'''
        // VANTA_LIBRARY_UI_R7: controller-first launcher navigation.
        if (vantaHandleControllerKey(event)) return true;
'''

MOTION_START = r'''
        // VANTA_LIBRARY_UI_R7: translate joystick/analog motion into launcher focus moves.
        if (vantaHandleAnalogNavigation(event)) return true;
'''

RESULT_START = r'''
        // VANTA_LIBRARY_UI_R7: persistent custom cover picker.
        if (requestCode == REQ_PICK_COVER) {
            try {
                if (resultCode == RESULT_OK && data != null && data.getData() != null &&
                    vantaCoverTargetGameUri != null) {
                    android.net.Uri cover = data.getData();
                    int takeFlags = data.getFlags() & android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION;
                    try {
                        getContentResolver().takePersistableUriPermission(cover, takeFlags);
                    } catch (Throwable ignored) {
                        // Some document providers grant access without persistable flags.
                    }
                    VantaPrefs.setCoverUri(this, vantaCoverTargetGameUri, cover.toString());
                    android.widget.Toast.makeText(this, "Capa salva no VANTA", android.widget.Toast.LENGTH_SHORT).show();
                    if (currentPage == Page.LIBRARY) renderLibrary();
                    else if (currentPage != null) show(currentPage);
                }
            } finally {
                vantaCoverTargetGameUri = null;
            }
            return;
        }
'''

RENDER_END = r'''
        // VANTA_LIBRARY_UI_R7: make a controller target available after a library refresh.
        vantaFocusFirstGameTileDeferred();
'''


def patch_activity(path: Path):
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        print("[skip] VantaActivity already has R7")
        return
    for required in ("gameTile", "dispatchKeyEvent", "onGenericMotionEvent", "onActivityResult", "renderLibrary"):
        find_method(src, required)

    op = class_body_open(src, "VantaActivity")
    src = src[:op + 1] + "\n" + ACTIVITY_FIELDS.rstrip() + "\n" + src[op + 1:]
    src = patch_game_tile_return(src)
    src = inject_method_start(src, "dispatchKeyEvent", DISPATCH_START)
    src = inject_method_start(src, "onGenericMotionEvent", MOTION_START)
    src = inject_method_start(src, "onActivityResult", RESULT_START)
    src = inject_method_end(src, "renderLibrary", RENDER_END)
    src = append_before_class_end(src, "VantaActivity", ACTIVITY_HELPERS)
    path.write_text(src, encoding="utf-8")
    print("[ok] VantaActivity controller navigation + covers")


def patch_prefs(path: Path):
    src = path.read_text(encoding="utf-8")
    if "static String coverUri(" in src:
        print("[skip] VantaPrefs already has cover metadata")
        return
    if "class VantaPrefs" not in src or "SharedPreferences" not in src:
        raise RuntimeError("Unexpected VantaPrefs source")
    src = append_before_class_end(src, "VantaPrefs", PREFS_HELPERS)
    path.write_text(src, encoding="utf-8")
    print("[ok] VantaPrefs cover metadata")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_vanta_library_r7.py <ppsspp-root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    activity = root / "android/src/org/ppsspp/ppsspp/VantaActivity.java"
    prefs = root / "android/src/org/ppsspp/ppsspp/VantaPrefs.java"
    if not activity.is_file() or not prefs.is_file():
        raise RuntimeError("VANTA launcher files not found; apply base VANTA layer first")
    patch_activity(activity)
    patch_prefs(prefs)
    print("[ok] VANTA Library UI R7 applied without touching scanner/core files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
