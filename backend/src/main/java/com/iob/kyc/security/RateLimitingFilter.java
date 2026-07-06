package com.iob.kyc.security;

import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.Bucket;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class RateLimitingFilter extends OncePerRequestFilter {

    private static final long BUCKET_TTL_MS = 10 * 60 * 1000L; // 10 minutes
    private final ConcurrentHashMap<String, BucketWrapper> buckets = new ConcurrentHashMap<>();

    private static class BucketWrapper {
        final Bucket bucket;
        volatile long lastAccessed;
        BucketWrapper(Bucket bucket) {
            this.bucket = bucket;
            this.lastAccessed = System.currentTimeMillis();
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        if (!path.startsWith("/api/")) return true;
        if (path.startsWith("/api/ai/")) return true;
        return false;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {

        cleanupExpiredBuckets();

        String ip = getClientIp(request);
        BucketWrapper wrapper = buckets.compute(ip, (key, existing) -> {
            if (existing != null && (System.currentTimeMillis() - existing.lastAccessed) < BUCKET_TTL_MS) {
                existing.lastAccessed = System.currentTimeMillis();
                return existing;
            }
            return new BucketWrapper(createBucket());
        });

        if (wrapper.bucket.tryConsume(1)) {
            filterChain.doFilter(request, response);
        } else {
            response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
            response.setContentType("application/json");
            response.getWriter().write("{\"success\":false,\"message\":\"Too many requests. Please try again later.\",\"statusCode\":429}");
        }
    }

    private void cleanupExpiredBuckets() {
        if (buckets.size() < 100) return;
        long now = System.currentTimeMillis();
        buckets.entrySet().removeIf(entry -> now - entry.getValue().lastAccessed > BUCKET_TTL_MS);
    }

    private Bucket createBucket() {
        Bandwidth limit = Bandwidth.builder().capacity(5000).refillGreedy(1000, Duration.ofMinutes(1)).build();
        return Bucket.builder().addLimit(limit).build();
    }

    private String getClientIp(HttpServletRequest request) {
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        if (xForwardedFor != null && !xForwardedFor.isEmpty()) {
            return xForwardedFor.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }
}
