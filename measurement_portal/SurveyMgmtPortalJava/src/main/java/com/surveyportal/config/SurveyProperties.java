package com.surveyportal.config;

import java.nio.file.Path;
import java.nio.file.Paths;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "survey")
public class SurveyProperties {

  private final Portal portal = new Portal();
  private int siteMainWidth = 934;
  private int siteMainHeight = 760;

  public Portal getPortal() {
    return portal;
  }

  public int getSiteMainWidth() {
    return siteMainWidth;
  }

  public void setSiteMainWidth(int siteMainWidth) {
    this.siteMainWidth = siteMainWidth;
  }

  public int getSiteMainHeight() {
    return siteMainHeight;
  }

  public void setSiteMainHeight(int siteMainHeight) {
    this.siteMainHeight = siteMainHeight;
  }

  /** Python 포털 루트 measurement_portal/SurveyMgmtPortal (data/site_media, data/*.sqlite3). */
  public static class Portal {
    private String home;

    public String getHome() {
      return home;
    }

    public void setHome(String home) {
      this.home = home;
    }
  }

  public Path resolvedPortalHome() {
    String raw = portal.getHome();
    if (raw == null || raw.isBlank()) {
      raw =
          Paths.get(System.getProperty("user.dir"))
              .resolve("../SurveyMgmtPortal")
              .normalize()
              .toString();
    }
    return Paths.get(raw.replace("\\", "/")).toAbsolutePath().normalize();
  }
}
