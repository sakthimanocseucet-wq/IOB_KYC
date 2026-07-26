package com.iob.kyc.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

@RestController
@RequestMapping("/api/ai")
public class AIProxyController {

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public AIProxyController() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(15000);
        factory.setReadTimeout(300000);
        this.restTemplate = new RestTemplate(factory);
    }

    @Value("${ai-service.url:http://localhost:5001}")
    private String aiServiceUrl;

    private String flaskBaseUrl() {
        return aiServiceUrl;
    }

    @PostMapping("/ocr")
    public void ocr(@RequestParam("image") MultipartFile image,
                    @RequestParam("doc_type") String docType,
                    HttpServletResponse response) throws IOException {
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("image", new org.springframework.core.io.ByteArrayResource(image.getBytes()) {
                @Override
                public String getFilename() {
                    return image.getOriginalFilename();
                }
            });
            body.add("doc_type", docType);

            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
            ResponseEntity<String> flaskResponse = restTemplate.exchange(
                    flaskBaseUrl() + "/api/ai/ocr", HttpMethod.POST, requestEntity, String.class);

            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (Exception e) {
            writeError(response, 500, e.getMessage());
        }
    }

    @PostMapping("/verify-and-liveness")
    public void verifyAndLiveness(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/verify-and-liveness", jsonBody, response);
    }

    @PostMapping("/face-verify")
    public void faceVerify(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/face-verify", jsonBody, response);
    }

    @PostMapping("/liveness/challenge")
    public void livenessChallenge(@RequestBody(required = false) String jsonBody, HttpServletResponse response) throws IOException {
        String body = Optional.ofNullable(jsonBody).orElse("{}");
        proxyJson(flaskBaseUrl() + "/api/ai/liveness/challenge", body, response);
    }

    @PostMapping("/liveness/verify-challenge")
    public void livenessVerifyChallenge(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/liveness/verify-challenge", jsonBody, response);
    }

    @PostMapping("/liveness/combined")
    public void livenessCombined(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/liveness/combined", jsonBody, response);
    }

    @PostMapping("/risk-score")
    public void riskScore(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/risk-score", jsonBody, response);
    }

    @PostMapping("/fraud-check")
    public void fraudCheck(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/fraud-check", jsonBody, response);
    }

    @PostMapping("/detailed-verify")
    public void detailedVerify(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/detailed-verify", jsonBody, response);
    }

    @PostMapping("/qr-verify")
    public void qrVerify(@RequestParam("image") MultipartFile image,
                         @RequestParam("ocr_data") String ocrData,
                         @RequestParam(value = "doc_type", defaultValue = "AADHAAR") String docType,
                         HttpServletResponse response) throws IOException {
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);

            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("image", new org.springframework.core.io.ByteArrayResource(image.getBytes()) {
                @Override
                public String getFilename() {
                    return image.getOriginalFilename();
                }
            });
            body.add("ocr_data", ocrData);
            body.add("doc_type", docType);

            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
            ResponseEntity<String> flaskResponse = restTemplate.exchange(
                    flaskBaseUrl() + "/api/ai/qr-verify", HttpMethod.POST, requestEntity, String.class);

            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (Exception e) {
            writeError(response, 500, e.getMessage());
        }
    }

    @PostMapping("/face-detect")
    public void faceDetect(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/face-detect", jsonBody, response);
    }

    @PostMapping("/qr-face-compare")
    public void qrFaceCompare(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        proxyJson(flaskBaseUrl() + "/api/ai/qr-face-compare", jsonBody, response);
    }

    @GetMapping("/health")
    public void health(HttpServletResponse response) throws IOException {
        try {
            ResponseEntity<String> flaskResponse = restTemplate.getForEntity(flaskBaseUrl() + "/health", String.class);
            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (Exception e) {
            response.setStatus(500);
            response.setContentType("application/json");
            Map<String, String> err = new java.util.HashMap<>();
            err.put("status", "error");
            err.put("service", "AI Proxy");
            err.put("detail", e.getMessage());
            response.getWriter().write(objectMapper.writeValueAsString(err));
        }
    }

    @GetMapping("/diagnose")
    public void diagnose(HttpServletResponse response) throws IOException {
        try {
            ResponseEntity<String> flaskResponse = restTemplate.getForEntity(flaskBaseUrl() + "/diagnose", String.class);
            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (Exception e) {
            response.setStatus(500);
            response.setContentType("application/json");
            Map<String, String> err = new java.util.HashMap<>();
            err.put("status", "error");
            err.put("service", "AI Proxy");
            err.put("detail", e.getMessage());
            response.getWriter().write(objectMapper.writeValueAsString(err));
        }
    }

    @GetMapping("/test-deepfake")
    public void testDeepfake(HttpServletResponse response) throws IOException {
        try {
            ResponseEntity<String> flaskResponse = restTemplate.getForEntity(flaskBaseUrl() + "/test-deepfake", String.class);
            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (Exception e) {
            response.setStatus(500);
            response.setContentType("application/json");
            Map<String, String> err = new java.util.HashMap<>();
            err.put("status", "error");
            err.put("service", "AI Proxy");
            err.put("detail", e.getMessage());
            response.getWriter().write(objectMapper.writeValueAsString(err));
        }
    }

    @PostMapping("/deepfake-test")
    public void deepfakeTest(@RequestBody String jsonBody, HttpServletResponse response) throws IOException {
        try {
            org.springframework.http.HttpHeaders headers = new org.springframework.http.HttpHeaders();
            headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
            org.springframework.http.HttpEntity<String> entity = new org.springframework.HttpEntity<>(jsonBody, headers);
            ResponseEntity<String> flaskResponse = restTemplate.postForEntity(flaskBaseUrl() + "/deepfake-test", entity, String.class);
            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (Exception e) {
            response.setStatus(500);
            response.setContentType("application/json");
            Map<String, String> err = new java.util.HashMap<>();
            err.put("status", "error");
            err.put("service", "AI Proxy");
            err.put("detail", e.getMessage());
            response.getWriter().write(objectMapper.writeValueAsString(err));
        }
    }

    /**
     * Stable production-ready health check endpoint.
     * Returns a fixed JSON payload so the frontend can reliably decide if AI is reachable.
     */
    @GetMapping("/healthz")
    public void healthz(HttpServletResponse response) throws IOException {
        response.setStatus(HttpStatus.OK.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write("{\"status\":\"UP\",\"service\":\"AI Verification Service\"}");
    }


    private void proxyJson(String url, String jsonBody, HttpServletResponse response) throws IOException {
        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<String> requestEntity = new HttpEntity<>(jsonBody, headers);
            ResponseEntity<String> flaskResponse = restTemplate.exchange(
                    url, HttpMethod.POST, requestEntity, String.class);

            response.setStatus(flaskResponse.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(flaskResponse.getBody());
        } catch (org.springframework.web.client.HttpStatusCodeException e) {
            response.setStatus(e.getStatusCode().value());
            response.setContentType("application/json");
            response.getWriter().write(e.getResponseBodyAsString());
        } catch (Exception e) {
            writeError(response, 500, e.getMessage());
        }
    }

    private void writeError(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        Map<String, Object> err = new java.util.HashMap<>();
        err.put("success", false);
        err.put("error", message);
        response.getWriter().write(objectMapper.writeValueAsString(err));
    }
}
