package com.iob.kyc;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.io.File;

@Component
public class FlaskServerManager implements CommandLineRunner {

    private static final Logger log = LoggerFactory.getLogger(FlaskServerManager.class);
    private Process flaskProcess;

    @Value("${ai-server.python-path:python}")
    private String pythonPath;

    @Value("${ai-server.script-path:../ai-ml/api_server.py}")
    private String scriptPath;

    @Value("${ai-server.port:5001}")
    private int port;

    @Override
    public void run(String... args) {
        new Thread(() -> startFlaskServer(), "flask-server-thread").start();
    }

    private void startFlaskServer() {
        try {
            File script = new File(scriptPath);
            if (!script.exists()) {
                log.warn("Flask script not found at: {}. Skipping auto-start.", script.getAbsolutePath());
                return;
            }

            log.info("Starting AI/ML Flask server on port {}...", port);
            ProcessBuilder pb = new ProcessBuilder(pythonPath, "-u", script.getAbsolutePath());
            pb.directory(script.getParentFile());
            pb.redirectErrorStream(true);
            flaskProcess = pb.start();

            new Thread(() -> {
                try (var reader = flaskProcess.inputReader()) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        log.info("[Flask] {}", line);
                    }
                } catch (Exception ignored) {}
            }, "flask-output-reader").start();

            log.info("Flask server process started. Waiting for it to be ready...");
            waitForReady(120);
            log.info("AI/ML Flask server is ready on port {}!", port);
        } catch (Exception e) {
            log.error("Failed to start Flask server: {}", e.getMessage());
        }
    }

    private void waitForReady(int maxSeconds) {
        long start = System.currentTimeMillis();
        long timeout = maxSeconds * 1000L;
        while (System.currentTimeMillis() - start < timeout) {
            try {
                var conn = new java.net.URI("http://localhost:" + port + "/health").toURL().openConnection();
                conn.setConnectTimeout(1000);
                conn.setReadTimeout(1000);
                if (((java.net.HttpURLConnection) conn).getResponseCode() == 200) return;
            } catch (Exception ignored) {}
            try { Thread.sleep(1000); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); return; }
        }
        log.warn("Flask server did not become ready within {} seconds", maxSeconds);
    }

    @PreDestroy
    public void stop() {
        if (flaskProcess != null && flaskProcess.isAlive()) {
            log.info("Stopping Flask server...");
            flaskProcess.destroyForcibly();
            log.info("Flask server stopped.");
        }
    }
}
