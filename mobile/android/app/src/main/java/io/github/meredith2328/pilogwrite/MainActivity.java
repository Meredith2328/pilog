package io.github.meredith2328.pilogwrite;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(PilogSecurePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
