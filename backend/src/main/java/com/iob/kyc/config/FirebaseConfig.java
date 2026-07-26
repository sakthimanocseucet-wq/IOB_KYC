package com.iob.kyc.config;

import com.google.auth.oauth2.GoogleCredentials;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

import jakarta.annotation.PostConstruct;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

@Configuration
public class FirebaseConfig {

    private static final Logger log = LoggerFactory.getLogger(FirebaseConfig.class);

    @Value("${firebase.service-account:}")
    private String serviceAccountJson;

    @Value("${firebase.project-id:}")
    private String projectId;

    @PostConstruct
    public void init() {
        if (serviceAccountJson == null || serviceAccountJson.isEmpty()) {
            log.warn("[Firebase] No service account configured — Firebase Phone Auth disabled");
            return;
        }
        try {
            FirebaseOptions options = FirebaseOptions.builder()
                    .setCredentials(GoogleCredentials.fromStream(
                            new ByteArrayInputStream(serviceAccountJson.getBytes(StandardCharsets.UTF_8))))
                    .setProjectId(projectId)
                    .build();
            FirebaseApp.initializeApp(options);
            log.info("[Firebase] Firebase Admin SDK initialized for project: {}", projectId);
        } catch (Exception e) {
            log.error("[Firebase] Failed to initialize: {}", e.getMessage());
        }
    }
}
