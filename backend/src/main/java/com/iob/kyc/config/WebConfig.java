package com.iob.kyc.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import jakarta.annotation.PostConstruct;
import java.io.File;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private static final Logger log = LoggerFactory.getLogger(WebConfig.class);

    @Value("${file.upload-dir:./uploads}")
    private String uploadBaseDir;

    @PostConstruct
    public void init() {
        File dir = new File(uploadBaseDir);
        if (!dir.exists()) {
            dir.mkdirs();
            log.info("[WebConfig] Created upload directory: {}", dir.getAbsolutePath());
        }
        log.info("[WebConfig] Upload base dir: {} (exists={})", dir.getAbsolutePath(), dir.exists());
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/**")
                .addResourceLocations("classpath:/static/")
                .setCacheControl(org.springframework.http.CacheControl.noStore().mustRevalidate())
                .resourceChain(true);

        String uploadPath = new File(uploadBaseDir).getAbsolutePath() + File.separator;
        registry.addResourceHandler("/uploads/**")
                .addResourceLocations("file:" + uploadPath)
                .setCacheControl(org.springframework.http.CacheControl.noStore().mustRevalidate())
                .resourceChain(true);
        log.info("[WebConfig] Mapped /uploads/** -> file:{}", uploadPath);
    }
}
