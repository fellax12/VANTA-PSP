#!/usr/bin/env python3
'''VANTA PSP UI R8 - safe layer on top of R7/R2.'''
from pathlib import Path
import re
import sys
import apply_vanta_library_r7 as r7

MARKER = 'VANTA_UI_R8'
COLORS = ('BG','PANEL','PANEL_2','STROKE','TEXT','MUTED','BLUE','CYAN','GREEN')


def replace_method_body(src, name, body):
    _, op, cl, _ = r7.find_method(src, name)
    return src[:op+1] + '\n' + body.strip('\n') + '\n' + src[cl:]


def inject_method_end(src, name, code):
    _, _, cl, _ = r7.find_method(src, name)
    return src[:cl] + '\n' + code.rstrip() + '\n' + src[cl:]


def inject_after_super_oncreate(src, code):
    _, op, cl, _ = r7.find_method(src, 'onCreate')
    body = src[op+1:cl]
    m = re.search(r'super\.onCreate\s*\([^;]*\)\s*;', body)
    if not m:
        raise RuntimeError('super.onCreate anchor not found')
    pos = op + 1 + m.end()
    return src[:pos] + '\n' + code.rstrip() + '\n' + src[pos:]


def unfinal_theme_colors(src):
    originals = {}
    for name in COLORS:
        pat = re.compile(r'(?m)^(?P<i>[ \t]*)private\s+static\s+final\s+int\s+' + re.escape(name) + r'\s*=\s*(?P<e>[^;]+);')
        m = pat.search(src)
        if not m:
            raise RuntimeError('theme color field not found: ' + name)
        originals[name] = m.group('e').strip()
        repl = m.group('i') + 'private static int ' + name + ' = ' + originals[name] + ';'
        src = src[:m.start()] + repl + src[m.end():]
    return src, originals


COVER_BODY = r'''
        if (raw == null || game == null) return raw;
        raw.setFocusable(true);
        raw.setFocusableInTouchMode(false);
        raw.setTag(VANTA_GAME_TILE_TAG + game.uri);
        raw.setContentDescription(game.name + ". Jogo PSP. Pressione A para abrir.");

        raw.setOnFocusChangeListener((view, focused) -> {
            view.animate().scaleX(focused ? 1.025f : 1.0f).scaleY(focused ? 1.025f : 1.0f).setDuration(105L).start();
            view.setAlpha(focused ? 1.0f : 0.96f);
            if (android.os.Build.VERSION.SDK_INT >= 21) view.setElevation(focused ? dp(8) : dp(1));
        });

        if (raw instanceof android.widget.LinearLayout) {
            android.widget.LinearLayout tile = (android.widget.LinearLayout) raw;
            java.util.ArrayList<android.view.View> old = new java.util.ArrayList<>();
            while (tile.getChildCount() > 0) {
                android.view.View child = tile.getChildAt(0);
                tile.removeViewAt(0);
                old.add(child);
            }

            tile.setOrientation(android.widget.LinearLayout.HORIZONTAL);
            tile.setGravity(android.view.Gravity.CENTER_VERTICAL);
            tile.setClipToPadding(false);

            int coverW = dp(compactTile ? 88 : 108);
            int coverH = dp(compactTile ? 118 : 142);
            android.widget.FrameLayout art = new android.widget.FrameLayout(this);
            art.setBackground(round(PANEL_2, dp(14), STROKE));
            if (android.os.Build.VERSION.SDK_INT >= 21) art.setClipToOutline(true);

            android.widget.TextView placeholder = new android.widget.TextView(this);
            placeholder.setText("VANTA\nPSP");
            placeholder.setGravity(android.view.Gravity.CENTER);
            placeholder.setTextColor(MUTED);
            placeholder.setTextSize(compactTile ? 13f : 15f);
            placeholder.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
            placeholder.setLetterSpacing(0.08f);
            placeholder.setBackground(gradient(PANEL_2, PANEL, STROKE, dp(14), dp(1)));
            art.addView(placeholder, new android.widget.FrameLayout.LayoutParams(-1, -1));

            String coverUri = VantaPrefs.coverUri(this, game.uri);
            if (coverUri != null && !coverUri.isEmpty()) {
                try {
                    android.widget.ImageView cover = new android.widget.ImageView(this);
                    cover.setScaleType(android.widget.ImageView.ScaleType.CENTER_CROP);
                    cover.setImageURI(android.net.Uri.parse(coverUri));
                    art.addView(cover, new android.widget.FrameLayout.LayoutParams(-1, -1));
                } catch (Throwable ignored) {}
            }

            android.widget.TextView edit = new android.widget.TextView(this);
            edit.setText((coverUri == null || coverUri.isEmpty()) ? "+ CAPA" : "EDITAR");
            edit.setTextColor(TEXT);
            edit.setTextSize(10f);
            edit.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
            edit.setGravity(android.view.Gravity.CENTER);
            edit.setSingleLine(true);
            edit.setPadding(dp(6), dp(5), dp(6), dp(5));
            edit.setBackground(round(android.graphics.Color.argb(225, 8, 12, 22), dp(8), STROKE));
            edit.setClickable(true);
            edit.setFocusable(false);
            edit.setOnClickListener(v -> vantaPickCover(game));
            android.widget.FrameLayout.LayoutParams editLp = new android.widget.FrameLayout.LayoutParams(-1, -2, android.view.Gravity.BOTTOM);
            editLp.setMargins(dp(6), dp(6), dp(6), dp(6));
            art.addView(edit, editLp);

            android.widget.LinearLayout body = new android.widget.LinearLayout(this);
            body.setOrientation(android.widget.LinearLayout.VERTICAL);
            body.setGravity(android.view.Gravity.CENTER_VERTICAL);
            for (android.view.View child : old) body.addView(child);

            android.widget.LinearLayout.LayoutParams artLp = new android.widget.LinearLayout.LayoutParams(coverW, coverH);
            artLp.setMargins(0, 0, dp(14), 0);
            tile.addView(art, artLp);
            tile.addView(body, new android.widget.LinearLayout.LayoutParams(0, -2, 1f));
            tile.setMinimumHeight(coverH + dp(24));
        }
        return raw;
'''


PREFS = r'''
    // ==================== VANTA_UI_R8 preferences ====================
    static String uiTheme(android.content.Context c) { return p(c).getString("vanta_ui_theme", "vanta"); }
    static void setUiTheme(android.content.Context c, String v) { p(c).edit().putString("vanta_ui_theme", v == null ? "vanta" : v).apply(); }
    static int displayRefreshRate(android.content.Context c) { return p(c).getInt("vanta_display_refresh_rate", 0); }
    static void setDisplayRefreshRate(android.content.Context c, int hz) { p(c).edit().putInt("vanta_display_refresh_rate", (hz == 60 || hz == 90) ? hz : 0).apply(); }
    static boolean showFps(android.content.Context c) { return p(c).getBoolean("vanta_show_fps", false); }
    static void setShowFps(android.content.Context c, boolean v) { p(c).edit().putBoolean("vanta_show_fps", v).apply(); }
    // ================== / VANTA_UI_R8 preferences ==================
'''


NATIVE_DECL = r'''
    // VANTA_UI_R8
    public static native void vantaApplyOverlayConfig(boolean showFps);
'''


CPP = r'''
// ==================== VANTA_UI_R8 FPS bridge ====================
extern "C" JNIEXPORT void JNICALL
Java_org_ppsspp_ppsspp_NativeApp_vantaApplyOverlayConfig(JNIEnv *, jclass, jboolean showFps) {
    constexpr int VANTA_FPS_COUNTER_FLAG = 1 << 1;
    if (showFps) g_Config.iShowStatusFlags |= VANTA_FPS_COUNTER_FLAG;
    else g_Config.iShowStatusFlags &= ~VANTA_FPS_COUNTER_FLAG;
}
// ================== / VANTA_UI_R8 FPS bridge ==================
'''


PPS_HELPERS = r'''
    // ==================== VANTA_UI_R8 display bridge ====================
    private void vantaApplyDisplayPreferences() {
        NativeApp.vantaApplyOverlayConfig(VantaPrefs.showFps(this));
        int target = VantaPrefs.displayRefreshRate(this);
        if (target <= 0) return;
        try {
            android.view.Display d = getWindowManager().getDefaultDisplay();
            android.view.Display.Mode current = d.getMode();
            android.view.Display.Mode best = null;
            float deltaBest = Float.MAX_VALUE;
            for (android.view.Display.Mode mode : d.getSupportedModes()) {
                if (mode.getPhysicalWidth() != current.getPhysicalWidth() || mode.getPhysicalHeight() != current.getPhysicalHeight()) continue;
                float delta = Math.abs(mode.getRefreshRate() - (float)target);
                if (delta < deltaBest) { deltaBest = delta; best = mode; }
            }
            android.view.WindowManager.LayoutParams lp = getWindow().getAttributes();
            lp.preferredRefreshRate = (float)target;
            if (best != null && deltaBest <= 5.0f) lp.preferredDisplayModeId = best.getModeId();
            getWindow().setAttributes(lp);
        } catch (Throwable t) {
            android.util.Log.w("VANTA", "refresh request failed", t);
        }
    }
    // ================== / VANTA_UI_R8 display bridge ==================
'''


def activity_helpers(original):
    defaults = '\n'.join('            %s = %s;' % (k, original[k]) for k in COLORS)
    return r'''
    // ==================== VANTA_UI_R8 ====================
    private void vantaApplyThemePalette() {
        String theme = VantaPrefs.uiTheme(this);
        if ("oled".equals(theme)) {
            BG=android.graphics.Color.rgb(0,0,0); PANEL=android.graphics.Color.rgb(8,11,18); PANEL_2=android.graphics.Color.rgb(15,20,31); STROKE=android.graphics.Color.rgb(42,51,69);
            TEXT=android.graphics.Color.rgb(247,249,253); MUTED=android.graphics.Color.rgb(145,155,178); BLUE=android.graphics.Color.rgb(104,122,255); CYAN=android.graphics.Color.rgb(50,215,255); GREEN=android.graphics.Color.rgb(67,231,166);
        } else if ("nebula".equals(theme)) {
            BG=android.graphics.Color.rgb(8,6,17); PANEL=android.graphics.Color.rgb(21,16,39); PANEL_2=android.graphics.Color.rgb(32,25,55); STROKE=android.graphics.Color.rgb(63,47,96);
            TEXT=android.graphics.Color.rgb(248,245,255); MUTED=android.graphics.Color.rgb(176,166,201); BLUE=android.graphics.Color.rgb(143,124,255); CYAN=android.graphics.Color.rgb(208,102,255); GREEN=android.graphics.Color.rgb(107,231,200);
        } else if ("cyber".equals(theme)) {
            BG=android.graphics.Color.rgb(4,15,14); PANEL=android.graphics.Color.rgb(10,27,24); PANEL_2=android.graphics.Color.rgb(16,41,36); STROKE=android.graphics.Color.rgb(33,75,67);
            TEXT=android.graphics.Color.rgb(236,255,249); MUTED=android.graphics.Color.rgb(142,184,173); BLUE=android.graphics.Color.rgb(34,199,169); CYAN=android.graphics.Color.rgb(53,242,208); GREEN=android.graphics.Color.rgb(101,240,138);
        } else if ("crimson".equals(theme)) {
            BG=android.graphics.Color.rgb(16,6,9); PANEL=android.graphics.Color.rgb(33,16,21); PANEL_2=android.graphics.Color.rgb(49,24,32); STROKE=android.graphics.Color.rgb(86,48,58);
            TEXT=android.graphics.Color.rgb(255,244,246); MUTED=android.graphics.Color.rgb(193,154,164); BLUE=android.graphics.Color.rgb(255,93,122); CYAN=android.graphics.Color.rgb(255,145,111); GREEN=android.graphics.Color.rgb(97,223,167);
        } else {
__DEFAULTS__
        }
    }

    private String vantaThemeLabel() {
        String t=VantaPrefs.uiTheme(this); if("oled".equals(t))return "OLED"; if("nebula".equals(t))return "NEBULA"; if("cyber".equals(t))return "CYBER"; if("crimson".equals(t))return "CRIMSON"; return "VANTA";
    }
    private String vantaRefreshLabel() { int h=VantaPrefs.displayRefreshRate(this); return h<=0?"AUTO":(h+" Hz"); }

    private android.widget.Button vantaR8Button(String s) {
        android.widget.Button b=new android.widget.Button(this); b.setText(s); b.setAllCaps(false); b.setTextColor(TEXT); b.setTextSize(12f); b.setTypeface(android.graphics.Typeface.DEFAULT_BOLD); b.setBackground(round(PANEL_2,dp(13),STROKE)); b.setMinHeight(0); b.setMinimumHeight(0); return b;
    }

    private android.widget.LinearLayout vantaPageColumn(android.view.View v) {
        if(v==null)return null;
        if(v instanceof android.widget.ScrollView){android.widget.ScrollView s=(android.widget.ScrollView)v; if(s.getChildCount()>0&&s.getChildAt(0) instanceof android.widget.LinearLayout)return (android.widget.LinearLayout)s.getChildAt(0);}
        if(v instanceof android.widget.LinearLayout){android.widget.LinearLayout l=(android.widget.LinearLayout)v; if(l.getOrientation()==android.widget.LinearLayout.VERTICAL)return l;}
        if(v instanceof android.view.ViewGroup){android.view.ViewGroup g=(android.view.ViewGroup)v; for(int i=0;i<g.getChildCount();i++){android.widget.LinearLayout hit=vantaPageColumn(g.getChildAt(i)); if(hit!=null)return hit;}}
        return null;
    }

    private boolean vantaTagged(android.view.View v,String wanted){if(v==null)return false; if(wanted.equals(v.getTag()))return true; if(v instanceof android.view.ViewGroup){android.view.ViewGroup g=(android.view.ViewGroup)v; for(int i=0;i<g.getChildCount();i++)if(vantaTagged(g.getChildAt(i),wanted))return true;} return false;}

    private void vantaInjectR8SettingsCard() {
        if(currentPage!=Page.HOME||content==null||content.getChildCount()==0)return;
        android.view.View page=content.getChildAt(0); String tag="vanta_r8_quick_settings"; if(vantaTagged(page,tag))return;
        android.widget.LinearLayout column=vantaPageColumn(page); if(column==null)return;
        android.widget.LinearLayout box=new android.widget.LinearLayout(this); box.setTag(tag); box.setOrientation(android.widget.LinearLayout.VERTICAL); box.setPadding(dp(18),dp(16),dp(18),dp(16)); box.setBackground(gradient(PANEL,PANEL_2,STROKE,dp(18),dp(1)));
        box.addView(text("DISPLAY & INTERFACE",12f,MUTED,true));
        android.widget.TextView info=text("FPS real do jogo • 60/90 Hz controla a tela, não a velocidade do jogo",12f,MUTED,false); android.widget.LinearLayout.LayoutParams ip=new android.widget.LinearLayout.LayoutParams(-1,-2); ip.setMargins(0,dp(4),0,dp(12)); box.addView(info,ip);
        android.widget.LinearLayout row=new android.widget.LinearLayout(this); row.setOrientation(android.widget.LinearLayout.HORIZONTAL);
        android.widget.Button fps=vantaR8Button(VantaPrefs.showFps(this)?"FPS • ON":"FPS • OFF"); fps.setOnClickListener(v->{boolean e=!VantaPrefs.showFps(this);VantaPrefs.setShowFps(this,e);fps.setText(e?"FPS • ON":"FPS • OFF");android.widget.Toast.makeText(this,"FPS aplicado ao abrir o jogo",android.widget.Toast.LENGTH_SHORT).show();});
        android.widget.Button hz=vantaR8Button("TELA • "+vantaRefreshLabel()); hz.setOnClickListener(v->{int c=VantaPrefs.displayRefreshRate(this);int n=c==0?60:(c==60?90:0);VantaPrefs.setDisplayRefreshRate(this,n);vantaApplyLauncherRefreshRate();hz.setText("TELA • "+vantaRefreshLabel());});
        android.widget.Button theme=vantaR8Button("TEMA • "+vantaThemeLabel()); theme.setOnClickListener(v->{String c=VantaPrefs.uiTheme(this);String n="vanta".equals(c)?"oled":("oled".equals(c)?"nebula":("nebula".equals(c)?"cyber":("cyber".equals(c)?"crimson":"vanta")));VantaPrefs.setUiTheme(this,n);recreate();});
        android.widget.LinearLayout.LayoutParams a=new android.widget.LinearLayout.LayoutParams(0,dp(46),1f);a.setMargins(0,0,dp(6),0);android.widget.LinearLayout.LayoutParams b=new android.widget.LinearLayout.LayoutParams(0,dp(46),1f);b.setMargins(dp(6),0,dp(6),0);android.widget.LinearLayout.LayoutParams c=new android.widget.LinearLayout.LayoutParams(0,dp(46),1f);c.setMargins(dp(6),0,0,0);row.addView(fps,a);row.addView(hz,b);row.addView(theme,c);box.addView(row);
        android.widget.LinearLayout.LayoutParams bp=new android.widget.LinearLayout.LayoutParams(-1,-2);bp.setMargins(0,dp(18),0,dp(4));column.addView(box,bp);
    }

    private void vantaApplyLauncherRefreshRate() {
        int target=VantaPrefs.displayRefreshRate(this);
        try { android.view.WindowManager.LayoutParams lp=getWindow().getAttributes(); if(target<=0){lp.preferredDisplayModeId=0;lp.preferredRefreshRate=0f;getWindow().setAttributes(lp);return;} android.view.Display d=getWindowManager().getDefaultDisplay();android.view.Display.Mode cur=d.getMode(),best=null;float bd=Float.MAX_VALUE;for(android.view.Display.Mode m:d.getSupportedModes()){if(m.getPhysicalWidth()!=cur.getPhysicalWidth()||m.getPhysicalHeight()!=cur.getPhysicalHeight())continue;float x=Math.abs(m.getRefreshRate()-(float)target);if(x<bd){bd=x;best=m;}}lp.preferredRefreshRate=(float)target;if(best!=null&&bd<=5f)lp.preferredDisplayModeId=best.getModeId();getWindow().setAttributes(lp);} catch(Throwable ignored){}
    }
    // ================== / VANTA_UI_R8 ==================
'''.replace('__DEFAULTS__', defaults)


def patch_activity(path):
    src=path.read_text(encoding='utf-8')
    if MARKER in src: return
    if 'VANTA_LIBRARY_UI_R7' not in src: raise RuntimeError('R7 must be applied before R8')
    src,original=unfinal_theme_colors(src)
    src=replace_method_body(src,'vantaPrepareGameTile',COVER_BODY)
    src=inject_after_super_oncreate(src,'        // VANTA_UI_R8\n        vantaApplyThemePalette();\n        vantaApplyLauncherRefreshRate();')
    src=inject_method_end(src,'show','        // VANTA_UI_R8\n        vantaInjectR8SettingsCard();')
    src=r7.append_before_class_end(src,'VantaActivity',activity_helpers(original))
    path.write_text(src,encoding='utf-8'); print('[ok] VantaActivity R8')


def patch_prefs(path):
    src=path.read_text(encoding='utf-8')
    if 'VANTA_UI_R8 preferences' not in src: src=r7.append_before_class_end(src,'VantaPrefs',PREFS)
    path.write_text(src,encoding='utf-8'); print('[ok] VantaPrefs R8')


def patch_native(path):
    src=path.read_text(encoding='utf-8')
    if 'vantaApplyOverlayConfig' not in src: src=r7.append_before_class_end(src,'NativeApp',NATIVE_DECL)
    path.write_text(src,encoding='utf-8'); print('[ok] NativeApp R8')


def patch_ppsspp(path):
    src=path.read_text(encoding='utf-8')
    if 'VANTA_UI_R8 display bridge' in src: return
    _,op,cl,_=r7.find_method(src,'onCreate'); body=src[op+1:cl]
    m=re.search(r'if\s*\(\s*!initialized\s*\)\s*\{\s*Initialize\s*\(\s*\)\s*;\s*initialized\s*=\s*true\s*;\s*\}',body,re.S)
    if not m: raise RuntimeError('PpssppActivity Initialize block not found')
    pos=op+1+m.end();src=src[:pos]+'\n\n\t\t// VANTA_UI_R8\n\t\tvantaApplyDisplayPreferences();'+src[pos:]
    src=r7.append_before_class_end(src,'PpssppActivity',PPS_HELPERS)
    path.write_text(src,encoding='utf-8'); print('[ok] PpssppActivity R8')


def patch_cpp(path):
    src=path.read_text(encoding='utf-8')
    if 'vantaApplyOverlayConfig' not in src: src=src.rstrip()+'\n\n'+CPP.strip()+'\n'
    path.write_text(src,encoding='utf-8'); print('[ok] app-android.cpp R8')


def main():
    if len(sys.argv)!=2: return 2
    root=Path(sys.argv[1]).resolve()
    files=[root/'android/src/org/ppsspp/ppsspp/VantaActivity.java',root/'android/src/org/ppsspp/ppsspp/VantaPrefs.java',root/'android/src/org/ppsspp/ppsspp/NativeApp.java',root/'android/src/org/ppsspp/ppsspp/PpssppActivity.java',root/'android/jni/app-android.cpp']
    for f in files:
        if not f.is_file(): raise RuntimeError('missing source: '+str(f))
    patch_activity(files[0]);patch_prefs(files[1]);patch_native(files[2]);patch_ppsspp(files[3]);patch_cpp(files[4])
    print('[ok] VANTA R8 applied; scanner/cheat sources untouched')
    return 0

if __name__=='__main__': raise SystemExit(main())
