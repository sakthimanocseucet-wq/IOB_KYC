package com.iob.kyc.controller;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/config")
public class ConfigController {

    @Value("${firebase.project-id:}")
    private String projectId;

    @Value("${firebase.api-key:}")
    private String apiKey;

    @Value("${firebase.auth-domain:}")
    private String authDomain;

    @GetMapping("/firebase")
    public ResponseEntity<Map<String, String>> getFirebaseConfig() {
        return ResponseEntity.ok(Map.of(
                "projectId", projectId != null ? projectId : "",
                "apiKey", apiKey != null ? apiKey : "",
                "authDomain", authDomain != null && !authDomain.isEmpty() ? authDomain : projectId + ".firebaseapp.com"
        ));
    }
}
