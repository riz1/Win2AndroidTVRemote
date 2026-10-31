package com.tvremote.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** A native Android screen over the existing Android TV Remote v2 protocol. */
public class MainActivity extends Activity {
    private static final int BG = Color.rgb(20,23,28), PANEL = Color.rgb(35,40,48),
        INK = Color.rgb(243,246,251), MUTED = Color.rgb(166,179,198), BLUE = Color.rgb(119,170,255);
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private PyObject engine;
    private SharedPreferences prefs;
    private boolean started, destroyed, connected, pollPending, ready;
    private LinearLayout content;
    private TextView title, status, volume, app;
    private EditText text;
    private Pad pad;
    private AlertDialog pairDialog, tvDialog;
    private NsdManager nsd;
    private NsdManager.DiscoveryListener discovery;
    private final ArrayDeque<NsdServiceInfo> resolveQueue = new ArrayDeque<>();
    private final HashSet<String> foundHosts = new HashSet<>();
    private boolean resolving;
    private int discoveryGeneration;
    private LinearLayout deviceList;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("remote", MODE_PRIVATE);
        nsd = (NsdManager) getSystemService(Context.NSD_SERVICE);
        buildUi();
        worker.execute(() -> {
            try {
                engine = Python.getInstance().getModule("remote_bridge")
                    .get("Engine").call(getFilesDir().getAbsolutePath());
                runOnUiThread(() -> { ready=true; if (started && !destroyed) reconnect(); });
            } catch (Exception e) { error(e); }
        });
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(radius)); return d;
    }
    private TextView label(String value, int size, int color) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        return view;
    }
    private LinearLayout row(LinearLayout parent) {
        LinearLayout view = new LinearLayout(this); view.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2); lp.bottomMargin=dp(10);
        parent.addView(view, lp); return view;
    }
    private Button button(LinearLayout parent, String label, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setAllCaps(false);
        button.setTextSize(14); button.setTextColor(INK); button.setMinWidth(0); button.setMinimumWidth(0);
        button.setPadding(dp(4),0,dp(4),0); button.setBackground(background(PANEL, 16));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, dp(48), 1); lp.setMargins(dp(3),0,dp(3),0);
        parent.addView(button,lp);
        button.setOnClickListener(v -> { v.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP); action.run(); });
        return button;
    }

    private void buildUi() {
        FrameLayout frame = new FrameLayout(this); frame.setBackgroundColor(BG);
        // Keep content outside status/navigation bars, including Android 15 edge-to-edge.
        frame.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                         insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true);
        frame.addView(scroll,new FrameLayout.LayoutParams(-1,-1));
        FrameLayout center = new FrameLayout(this); scroll.addView(center);
        content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(18),dp(16),dp(18),dp(16));
        FrameLayout.LayoutParams body = new FrameLayout.LayoutParams(
            Math.min(getResources().getDisplayMetrics().widthPixels, dp(430)), -2, Gravity.TOP|Gravity.CENTER_HORIZONTAL);
        center.addView(content,body);
        LinearLayout header = row(content);
        LinearLayout names = new LinearLayout(this); names.setOrientation(LinearLayout.VERTICAL);
        header.addView(names,new LinearLayout.LayoutParams(0,-2,2));
        title=label(prefs.getString("name","TV Remote"),21,INK); title.setTypeface(null,Typeface.BOLD); names.addView(title);
        app=label("Your TV, a little closer.",13,MUTED); names.addView(app);
        button(header,"TVs",this::showTvs);
        LinearLayout top = row(content);
        Button power=button(top,"Power",()->key("POWER")); power.setTextColor(Color.rgb(255,176,174));
        button(top,"Input",()->key("TV_INPUT")); button(top,"Settings",()->key("SETTINGS"));
        LinearLayout modes = row(content);
        Button remote = button(modes,"Remote",()->{}), touch = button(modes,"Touchpad",()->{});
        remote.setTextColor(BLUE);
        remote.setOnClickListener(v->{pad.touch=false; pad.invalidate(); remote.setTextColor(BLUE); touch.setTextColor(INK);});
        touch.setOnClickListener(v->{pad.touch=true; pad.invalidate(); touch.setTextColor(BLUE); remote.setTextColor(INK);});
        pad = new Pad(this); content.addView(pad,new LinearLayout.LayoutParams(-1,dp(250)));
        LinearLayout nav=row(content);
        button(nav,"Back",()->key("BACK")); button(nav,"Home",()->key("HOME")); button(nav,"Menu",()->key("MENU"));
        LinearLayout media=row(content);
        button(media,"−",()->key("VOLUME_DOWN")); button(media,"Mute",()->key("VOLUME_MUTE"));
        button(media,"+",()->key("VOLUME_UP")); button(media,"Play / Pause",()->key("MEDIA_PLAY_PAUSE"));
        volume=label("Volume —",12,MUTED); volume.setGravity(Gravity.CENTER); content.addView(volume);
        LinearLayout apps=row(content); apps.setPadding(0,dp(10),0,0);
        button(apps,"YouTube",()->send("app","https://www.youtube.com"));
        TextView keyboard=label("TYPE ON TV",12,MUTED); keyboard.setPadding(0,dp(6),0,dp(4)); content.addView(keyboard);
        text=new EditText(this); text.setSingleLine(true); text.setTextColor(INK); text.setHintTextColor(MUTED);
        text.setTextSize(16); text.setHint("Select a text field on your TV first");
        text.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        text.setImeOptions(EditorInfo.IME_ACTION_GO | EditorInfo.IME_FLAG_NO_EXTRACT_UI);
        content.addView(text,new LinearLayout.LayoutParams(-1,dp(52)));
        text.setOnEditorActionListener((v, action, event)->{
            if(action==EditorInfo.IME_ACTION_GO || (event!=null && event.getKeyCode()==KeyEvent.KEYCODE_ENTER && event.getAction()==KeyEvent.ACTION_DOWN)) {
                submitText(true); return true;
            } return false;
        });
        LinearLayout typing=row(content);
        button(typing,"Clear",()->text.setText("")); button(typing,"Send text",()->submitText(false)); button(typing,"Enter",()->submitText(true));
        status=label("Starting…",13,MUTED); status.setGravity(Gravity.CENTER); status.setPadding(0,dp(6),0,0); content.addView(status);
        setContentView(frame);
    }

    private void call(String method, Object... args) {
        if(destroyed) return;
        worker.execute(()->{try {if(engine!=null) engine.callAttr(method,args);} catch(Exception e){error(e);}});
    }
    private void error(Exception e) {
        runOnUiThread(()->{if(!destroyed) status.setText("Error: " + e.getMessage());});
    }
    private void key(String key) { send("key",key); }
    private void send(String type, String value) {
        if(!connected) { Toast.makeText(this,"Connect to a TV first",Toast.LENGTH_SHORT).show(); return; }
        call("send",type,value);
    }
    private void submitText(boolean enter) {
        if(!connected) {send("text",""); return;}
        String value=text.getText().toString();
        if(!value.isEmpty()) send("text",value);
        if(enter) key("ENTER");
        text.setText("");
    }
    private void reconnect() {
        String host=prefs.getString("host","");
        if(!host.isEmpty()) call("connect",host); else status.setText("Tap TVs to connect. Use the same Wi-Fi as your TV.");
    }
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if(!started || destroyed) return;
            if(!pollPending) {
                pollPending=true;
                worker.execute(()->{
                    try {
                        String result=engine==null ? "[]" : engine.callAttr("poll").toString();
                        runOnUiThread(()->{
                            pollPending=false;
                            if(!started || destroyed) return;
                            try {
                                JSONArray events=new JSONArray(result);
                                for(int i=0;i<events.length();i++) handle(events.getJSONArray(i));
                            } catch(Exception e){error(e);}
                        });
                    } catch(Exception e){runOnUiThread(()->pollPending=false);error(e);}
                });
            }
            handler.postDelayed(this,200);
        }
    };
    private void handle(JSONArray event) throws Exception {
        String kind=event.getString(0);
        switch(kind) {
            case "connected":
                connected=event.getBoolean(1); status.setText(connected?"● Connected":"Not connected");
                status.setTextColor(connected?Color.rgb(62,207,110):MUTED);
                if(!connected) {volume.setText("Volume —");app.setText("Choose a TV or reconnect");}
                else app.setText("Ready to watch");
                break;
            case "status": case "error": status.setText(event.optString(1)); break;
            case "volume":
                JSONObject value=event.getJSONObject(1);
                volume.setText(value.optBoolean("muted")?"Muted":"Volume "+value.optInt("level")+" / "+value.optInt("max")); break;
            case "app":
                String name=event.optString(1);
                if(name.contains("youtube")) name="YouTube"; else if(name.contains("netflix")) name="Netflix";
                else if(name.contains("launcher")) name="Home"; else name=name.substring(name.lastIndexOf('.')+1);
                app.setText(name); break;
            case "need_pair":
                if(pairDialog!=null) break;
                pairDialog=new AlertDialog.Builder(this).setTitle("Pair with your TV")
                    .setMessage("A six-character code will appear on the TV.")
                    .setPositiveButton("Pair",(d,w)->call("pair"))
                    .setNegativeButton("Cancel",(d,w)->call("suspend")).create();
                pairDialog.setOnDismissListener(d->pairDialog=null); pairDialog.show(); break;
            case "pair_code": showCode(event.optString(1)); break;
        }
    }
    private void showCode(String message) {
        if(pairDialog!=null) pairDialog.dismiss();
        EditText code=new EditText(this); code.setSingleLine(true);
        code.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS|InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        code.setHint("A1B2C3"); code.setPadding(dp(24),dp(12),dp(24),dp(12));
        pairDialog=new AlertDialog.Builder(this).setTitle("Pairing code").setMessage(message).setView(code)
            .setPositiveButton("Connect",(d,w)->call("finish_pairing",code.getText().toString()))
            .setNegativeButton("Cancel",(d,w)->call("suspend")).create();
        pairDialog.setOnCancelListener(d->call("suspend"));
        pairDialog.setOnDismissListener(d->pairDialog=null); pairDialog.show();
    }

    private void showTvs() {
        if(tvDialog!=null) return;
        LinearLayout layout=new LinearLayout(this); layout.setOrientation(LinearLayout.VERTICAL); layout.setPadding(dp(18),0,dp(18),0);
        TextView hint=label("Same Wi-Fi as your TV. Searching nearby…",14,MUTED); layout.addView(hint);
        ScrollView scroll=new ScrollView(this); deviceList=new LinearLayout(this); deviceList.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(deviceList); layout.addView(scroll,new LinearLayout.LayoutParams(-1,dp(170)));
        EditText address=new EditText(this); address.setSingleLine(true); address.setHint("TV IP address");
        address.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI); address.setText(prefs.getString("host",""));
        layout.addView(address);
        tvDialog=new AlertDialog.Builder(this).setTitle("Choose a TV").setView(layout)
            .setPositiveButton("Connect",null).setNegativeButton("Cancel",null).create();
        tvDialog.setOnDismissListener(d->{stopDiscovery(); tvDialog=null;});
        tvDialog.show();
        tvDialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            String host=address.getText().toString().trim();
            if(host.isEmpty() || host.contains("/") || host.contains(" ")) {address.setError("Enter the TV's IP address or hostname");return;}
            connect(host,host);
        });
        startDiscovery();
    }
    private void connect(String host, String name) {
        prefs.edit().putString("host",host).putString("name",name).apply();
        title.setText(name); text.setText(""); connected=false;
        if(tvDialog!=null) tvDialog.dismiss();
        call("connect",host);
    }
    private void startDiscovery() {
        stopDiscovery(); foundHosts.clear(); final int generation=discoveryGeneration;
        discovery=new NsdManager.DiscoveryListener() {
            public void onDiscoveryStarted(String type) {}
            public void onDiscoveryStopped(String type) {}
            public void onStartDiscoveryFailed(String type,int error){runOnUiThread(()->{if(generation==discoveryGeneration) stopDiscovery();});}
            public void onStopDiscoveryFailed(String type,int error) {}
            public void onServiceLost(NsdServiceInfo service) {}
            public void onServiceFound(NsdServiceInfo service) {runOnUiThread(()->{
                if(generation!=discoveryGeneration) return;
                resolveQueue.add(service); resolveNext(generation);
            });}
        };
        try {nsd.discoverServices("_androidtvremote2._tcp.",NsdManager.PROTOCOL_DNS_SD,discovery);}
        catch(Exception e) {stopDiscovery();}
        handler.postDelayed(()->{if(generation==discoveryGeneration) stopDiscovery();},10000);
    }
    private void resolveNext(int generation) {
        if(resolving || resolveQueue.isEmpty() || generation!=discoveryGeneration) return;
        resolving=true;
        nsd.resolveService(resolveQueue.remove(),new NsdManager.ResolveListener(){
            public void onResolveFailed(NsdServiceInfo service,int error){runOnUiThread(()->{
                if(generation!=discoveryGeneration) return; resolving=false;resolveNext(generation);
            });}
            public void onServiceResolved(NsdServiceInfo service){runOnUiThread(()->{
                if(generation!=discoveryGeneration) return;
                resolving=false;
                if(tvDialog!=null && service.getHost()!=null) {
                    String host=service.getHost().getHostAddress(), name=service.getServiceName();
                    if(foundHosts.add(host)) {
                        Button found=new Button(MainActivity.this);found.setAllCaps(false);found.setText(name+"\n"+host);
                        found.setOnClickListener(v->connect(host,name));deviceList.addView(found);
                    }
                }
                resolveNext(generation);
            });}
        });
    }
    private void stopDiscovery() {
        discoveryGeneration++; resolveQueue.clear(); resolving=false;
        if(discovery!=null) {try{nsd.stopServiceDiscovery(discovery);}catch(Exception ignored){} discovery=null;}
    }

    @Override protected void onStart(){super.onStart();started=true;handler.post(poll);if(ready)reconnect();}
    @Override public void onConfigurationChanged(android.content.res.Configuration config){
        super.onConfigurationChanged(config);
        content.getLayoutParams().width=Math.min(getResources().getDisplayMetrics().widthPixels,dp(430));
        content.requestLayout();
    }
    @Override protected void onStop(){
        started=false;handler.removeCallbacks(poll);stopDiscovery();
        if(tvDialog!=null) tvDialog.dismiss(); if(pairDialog!=null) pairDialog.dismiss();
        connected=false;call("suspend");super.onStop();
    }
    @Override protected void onDestroy(){
        destroyed=true;handler.removeCallbacksAndMessages(null);
        worker.execute(()->{if(engine!=null)engine.callAttr("close");});worker.shutdown();super.onDestroy();
    }
    @Override public boolean onKeyDown(int code,KeyEvent event){
        if(connected && (code==KeyEvent.KEYCODE_VOLUME_UP || code==KeyEvent.KEYCODE_VOLUME_DOWN)) {
            key(code==KeyEvent.KEYCODE_VOLUME_UP?"VOLUME_UP":"VOLUME_DOWN");return true;
        } return super.onKeyDown(code,event);
    }

    private class Pad extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        boolean touch, moved; float startX,startY,anchorX,anchorY;
        Pad(Context context){super(context);setContentDescription("TV navigation pad: up, down, left, right, and OK");setFocusable(true);}
        void circle(Canvas c,float x,float y,float radius,int color){paint.setColor(color);c.drawCircle(x,y,radius,paint);}
        void word(Canvas c,String text,float x,float y,int size,int color){paint.setColor(color);paint.setTextSize(dp(size));paint.setTextAlign(Paint.Align.CENTER);c.drawText(text,x,y-(paint.ascent()+paint.descent())/2,paint);}
        @Override protected void onDraw(Canvas c){
            float x=getWidth()/2f,y=getHeight()/2f;
            if(touch){paint.setColor(PANEL);c.drawRoundRect(dp(4),dp(8),getWidth()-dp(4),getHeight()-dp(8),dp(22),dp(22),paint);
                word(c,"Swipe to navigate",x,y-dp(12),17,INK);word(c,"Tap for OK · Long press for Back",x,y+dp(20),12,MUTED);
            } else {
                circle(c,x,y,dp(112),Color.rgb(13,16,20));circle(c,x,y,dp(108),PANEL);
                word(c,"⌃",x,y-dp(77),32,INK);word(c,"⌄",x,y+dp(77),32,INK);
                word(c,"‹",x-dp(77),y,32,INK);word(c,"›",x+dp(77),y,32,INK);
                circle(c,x,y,dp(45),BLUE);word(c,"OK",x,y,20,BG);
            }
        }
        @Override public boolean performClick(){super.performClick();return true;}
        @Override public boolean onTouchEvent(MotionEvent e){
            float x=e.getX(),y=e.getY();
            if(e.getAction()==MotionEvent.ACTION_DOWN){startX=anchorX=x;startY=anchorY=y;moved=false;getParent().requestDisallowInterceptTouchEvent(true);return true;}
            if(e.getAction()==MotionEvent.ACTION_MOVE){
                if(Math.max(Math.abs(x-startX),Math.abs(y-startY))>dp(8))moved=true;
                float dx=x-anchorX,dy=y-anchorY;
                if(touch && Math.max(Math.abs(dx),Math.abs(dy))>dp(40)){
                    key(Math.abs(dx)>Math.abs(dy)?(dx>0?"DPAD_RIGHT":"DPAD_LEFT"):(dy>0?"DPAD_DOWN":"DPAD_UP"));
                    anchorX=x;anchorY=y;performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
                }return true;
            }
            if(e.getAction()==MotionEvent.ACTION_UP){
                getParent().requestDisallowInterceptTouchEvent(false);performClick();
                if(!moved){
                    if(touch)key(e.getEventTime()-e.getDownTime()>600?"BACK":"DPAD_CENTER");
                    else {float dx=x-getWidth()/2f,dy=y-getHeight()/2f,d=dx*dx+dy*dy;
                        if(d<=dp(45)*dp(45))key("DPAD_CENTER");
                        else if(d<=dp(112)*dp(112))key(Math.abs(dx)>Math.abs(dy)?(dx>0?"DPAD_RIGHT":"DPAD_LEFT"):(dy>0?"DPAD_DOWN":"DPAD_UP"));
                    }performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP);
                }return true;
            }
            if(e.getAction()==MotionEvent.ACTION_CANCEL){getParent().requestDisallowInterceptTouchEvent(false);return true;}
            return true;
        }
    }
}
