package com.iob.kyc.config;

import com.iob.kyc.security.JwtAuthenticationFilter;
import com.iob.kyc.security.RateLimitingFilter;
import com.iob.kyc.service.CustomUserDetailsService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.http.HttpMethod;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfig {

    private final JwtAuthenticationFilter jwtAuthenticationFilter;
    private final RateLimitingFilter rateLimitingFilter;

    public SecurityConfig(JwtAuthenticationFilter jwtAuthenticationFilter, RateLimitingFilter rateLimitingFilter) {
        this.jwtAuthenticationFilter = jwtAuthenticationFilter;
        this.rateLimitingFilter = rateLimitingFilter;
    }

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .headers(headers -> headers.frameOptions(f -> f.sameOrigin()))
            .cors(cors -> cors.configurationSource(corsConfigurationSource()))
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(ctx -> ctx.securityContextRepository(new RequestAttributeSecurityContextRepository()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/index.html", "/project-report.html", "/PROJECT_REPORT.html", "/css/**", "/js/**", "/assets/**", "/user/**", "/admin/**", "/api/public/**", "/api/ai/healthz", "/api/ai/diagnose", "/api/ai/test-deepfake", "/api/ai/deepfake-test", "/api/config/**", "/health", "/error").permitAll()
                .requestMatchers("/api/auth/**").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/admin/applications/*/selfie", "/api/admin/applications/*/photo", "/api/admin/applications/*/aadhaar-front", "/api/admin/applications/*/aadhaar-back", "/api/admin/applications/*/pan-card", "/api/admin/applications/*/document").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin/applications/*/selfie", "/api/admin/applications/*/photo", "/api/admin/applications/*/aadhaar-front", "/api/admin/applications/*/aadhaar-back", "/api/admin/applications/*/pan-card", "/api/admin/applications/*/document").permitAll()
                .requestMatchers("/api/admin/**").hasAnyRole("ADMIN", "MANAGER", "OFFICER")
                .requestMatchers(HttpMethod.GET, "/api/kyc/branches").permitAll()
                .requestMatchers("/api/kyc/**").hasAnyRole("USER", "ADMIN")
                .anyRequest().authenticated()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, authException) -> {
                    String path = request.getServletPath();
                    if (path.startsWith("/api/")) {
                        response.setStatus(401);
                        response.setContentType("application/json");
                        response.getWriter().write("{\"success\":false,\"message\":\"Unauthorized - please login\",\"statusCode\":401}");
                    } else if (path.contains("/admin")) {
                        response.sendRedirect("/admin/login.html");
                    } else {
                        response.sendRedirect("/user/login.html");
                    }
                })
            )
            .addFilterBefore(rateLimitingFilter, UsernamePasswordAuthenticationFilter.class)
            .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("http://localhost:5500", "http://127.0.0.1:5500", "http://localhost:8080", "http://127.0.0.1:8080", "https://iobkyc-production.up.railway.app"));
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(CustomUserDetailsService userDetailsService, PasswordEncoder passwordEncoder) throws Exception {
        DaoAuthenticationProvider authProvider = new DaoAuthenticationProvider();
        authProvider.setUserDetailsService(userDetailsService);
        authProvider.setPasswordEncoder(passwordEncoder);
        return new org.springframework.security.authentication.ProviderManager(authProvider);
    }
}
