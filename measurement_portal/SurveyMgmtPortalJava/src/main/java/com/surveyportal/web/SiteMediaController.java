package com.surveyportal.web;

import com.surveyportal.config.SurveyProperties;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@Controller
public class SiteMediaController {

  private final SurveyProperties surveyProperties;

  public SiteMediaController(SurveyProperties surveyProperties) {
    this.surveyProperties = surveyProperties;
  }

  /** Python {@code /site-media/<site_id>/<file>} 과 동일. */
  @GetMapping("/site-media/{siteId}/{filename:.+}")
  public ResponseEntity<Resource> serve(
      @PathVariable String siteId, @PathVariable String filename) throws Exception {
    String fn = URLDecoder.decode(filename, StandardCharsets.UTF_8);
    if (!siteId.matches("\\d+")) {
      return ResponseEntity.notFound().build();
    }
    String low = fn.toLowerCase(Locale.ROOT);
    if (!low.endsWith(".jpg")
        && !low.endsWith(".jpeg")
        && !low.endsWith(".png")
        && !low.endsWith(".webp")) {
      return ResponseEntity.notFound().build();
    }
    Path base =
        surveyProperties.resolvedPortalHome().resolve("data/site_media").resolve(siteId).normalize();
    Path cand = base.resolve(fn).normalize();
    if (!cand.startsWith(base) || !Files.isRegularFile(cand)) {
      return ResponseEntity.notFound().build();
    }
    byte[] bytes = Files.readAllBytes(cand);
    Resource body = new ByteArrayResource(bytes);
    MediaType mt =
        low.endsWith(".png")
            ? MediaType.IMAGE_PNG
            : low.endsWith(".webp") ? MediaType.parseMediaType("image/webp") : MediaType.IMAGE_JPEG;
    return ResponseEntity.ok()
        .header(HttpHeaders.CACHE_CONTROL, "public, max-age=86400")
        .contentType(mt)
        .body(body);
  }
}
