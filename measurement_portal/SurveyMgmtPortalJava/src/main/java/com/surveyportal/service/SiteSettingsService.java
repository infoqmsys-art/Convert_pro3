package com.surveyportal.service;

import com.surveyportal.config.SurveyProperties;
import com.surveyportal.domain.Site;
import com.surveyportal.domain.SiteSmsConfig;
import com.surveyportal.domain.SiteSmsRecipient;
import com.surveyportal.repo.SiteRepository;
import com.surveyportal.repo.SiteSmsConfigRepository;
import com.surveyportal.repo.SiteSmsRecipientRepository;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;
import javax.imageio.ImageIO;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class SiteSettingsService {

  private static final Pattern INSTALL_DATE =
      Pattern.compile("\\d{4}-\\d{2}-\\d{2}");
  private static final Pattern SITE_CODE = Pattern.compile("[a-z0-9]{1,64}");

  private final SiteRepository siteRepository;
  private final SiteSmsConfigRepository smsConfigRepository;
  private final SiteSmsRecipientRepository recipientRepository;
  private final SurveyProperties surveyProperties;

  public SiteSettingsService(
      SiteRepository siteRepository,
      SiteSmsConfigRepository smsConfigRepository,
      SiteSmsRecipientRepository recipientRepository,
      SurveyProperties surveyProperties) {
    this.siteRepository = siteRepository;
    this.smsConfigRepository = smsConfigRepository;
    this.recipientRepository = recipientRepository;
    this.surveyProperties = surveyProperties;
  }

  public Site getSiteOrThrow(Long siteId) {
    return siteRepository.findById(siteId).orElseThrow();
  }

  public SiteSmsConfig getOrEmptySmsConfig(Long siteId) {
    return smsConfigRepository
        .findBySiteId(siteId)
        .orElseGet(
            () -> {
              SiteSmsConfig c = new SiteSmsConfig();
              c.setSiteId(siteId);
              c.setEnabled(0);
              c.setMessageTemplate("");
              c.setTimeFrom("00:00:00");
              c.setTimeTo("23:59:59");
              return c;
            });
  }

  public List<SiteSmsRecipient> listRecipients(Long siteId) {
    return recipientRepository.findBySiteIdOrderBySortOrderAscIdAsc(siteId);
  }

  public SiteSmsRecipient getRecipientOrThrow(Long siteId, Long recipientId) {
    SiteSmsRecipient r =
        recipientRepository.findById(recipientId).orElseThrow();
    if (!r.getSiteId().equals(siteId)) {
      throw new IllegalArgumentException("invalid recipient");
    }
    return r;
  }

  @Transactional
  public void saveSite(
      Long siteId,
      String name,
      String rawSiteCode,
      String rawInstall,
      String address,
      String siteProgram,
      String memo,
      MultipartFile imageMain,
      MultipartFile imageList)
      throws SiteSaveException {
    Site site = getSiteOrThrow(siteId);
    Long orgId = site.getOrganizationId();

    if (name == null || name.isBlank()) {
      throw new SiteSaveException("현장명은 필수입니다.");
    }

    String engCode = normalizeSiteCode(rawSiteCode);
    if (rawSiteCode != null && !rawSiteCode.isBlank() && engCode == null) {
      throw new SiteSaveException("현장 영문 코드는 소문자·숫자 1~64자만 허용됩니다.");
    }
    if (!isSiteCodeAvailable(orgId, engCode, siteId)) {
      throw new SiteSaveException("해당 업체에 이미 같은 영문 코드의 현장이 있습니다.");
    }

    String install;
    if (rawInstall == null || rawInstall.isBlank()) {
      install = null;
    } else if (INSTALL_DATE.matcher(rawInstall.trim()).matches()) {
      install = rawInstall.trim();
    } else {
      throw new SiteSaveException("설치일은 YYYY-MM-DD 형식이어야 합니다.");
    }

    if (!isSiteNameAvailable(orgId, name.trim(), siteId)) {
      throw new SiteSaveException("같은 업체에 동일한 현장명이 이미 있습니다.");
    }

    site.setName(name.trim());
    site.setSiteCode(engCode);
    site.setInstallDate(install);
    site.setAddress(address != null ? address.trim() : "");
    site.setSiteProgram(siteProgram != null ? siteProgram.trim() : "");
    site.setMemo(memo != null ? memo.trim() : "");

    try {
      siteRepository.save(site);
    } catch (DataIntegrityViolationException ex) {
      throw new SiteSaveException("같은 업체에 같은 현장명이거나 영문 코드가 충돌합니다.");
    }

    Path mediaRoot = mediaRoot();
    String newMain = null;
    String newList = null;
    if (imageMain != null && !imageMain.isEmpty()) {
      newMain = persistMainImage(siteId, imageMain, mediaRoot);
    }
    if (imageList != null && !imageList.isEmpty()) {
      newList = persistListImage(siteId, imageList, mediaRoot);
    }
    if (newMain != null) {
      site.setImageMain(newMain);
    }
    if (newList != null) {
      site.setImageList(newList);
    }
    if (newMain != null || newList != null) {
      siteRepository.save(site);
    }
  }

  @Transactional
  public void saveSms(Long siteId, boolean enabled, String message, String timeFrom, String timeTo) {
    getSiteOrThrow(siteId);
    SiteSmsConfig c =
        smsConfigRepository.findBySiteId(siteId).orElseGet(SiteSmsConfig::new);
    c.setSiteId(siteId);
    c.setEnabled(enabled ? 1 : 0);
    c.setMessageTemplate(message != null ? message : "");
    c.setTimeFrom(blankToDefault(timeFrom, "00:00:00"));
    c.setTimeTo(blankToDefault(timeTo, "23:59:59"));
    c.setUpdatedAt(nowSqliteUtc());
    smsConfigRepository.save(c);
  }

  @Transactional
  public void saveRecipient(
      Long siteId,
      Long recipientId,
      boolean sendEnabled,
      String name,
      String phone,
      String jobTitle,
      String department,
      String info)
      throws SiteSaveException {
    getSiteOrThrow(siteId);
    if (name == null || name.isBlank() || phone == null || phone.isBlank()) {
      throw new SiteSaveException("이름과 전화번호는 필수입니다.");
    }
    SiteSmsRecipient r;
    if (recipientId != null) {
      r = getRecipientOrThrow(siteId, recipientId);
    } else {
      r = new SiteSmsRecipient();
      r.setSiteId(siteId);
      int next =
          recipientRepository.findBySiteIdOrderBySortOrderAscIdAsc(siteId).stream()
              .mapToInt(rc -> Objects.requireNonNullElse(rc.getSortOrder(), 0))
              .max()
              .orElse(-1)
              + 1;
      r.setSortOrder(next);
      r.setCreatedAt(nowSqliteUtc());
    }
    r.setSendEnabled(sendEnabled ? 1 : 0);
    r.setName(name.trim());
    r.setPhone(phone.trim());
    r.setJobTitle(jobTitle != null ? jobTitle.trim() : "");
    r.setDepartment(department != null ? department.trim() : "");
    r.setInfo(info != null ? info.trim() : "");
    recipientRepository.save(r);
  }

  @Transactional
  public void deleteRecipient(Long siteId, Long recipientId) {
    recipientRepository.deleteByIdAndSiteId(recipientId, siteId);
  }

  private String blankToDefault(String s, String def) {
    if (s == null || s.isBlank()) {
      return def;
    }
    return s.trim();
  }

  private String nowSqliteUtc() {
    return DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss")
        .withZone(ZoneOffset.UTC)
        .format(Instant.now());
  }

  private Path mediaRoot() {
    return surveyProperties.resolvedPortalHome().resolve("data/site_media").normalize();
  }

  private String persistMainImage(long siteId, MultipartFile file, Path mediaRoot) throws SiteSaveException {
    byte[] raw;
    try {
      raw = file.getBytes();
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    BufferedImage im;
    try {
      im = ImageIO.read(new java.io.ByteArrayInputStream(raw));
    } catch (IOException e) {
      throw new SiteSaveException("메인 이미지를 읽을 수 없습니다.");
    }
    if (im == null) {
      throw new SiteSaveException("메인 이미지 형식이 지원되지 않습니다.");
    }
    int w = surveyProperties.getSiteMainWidth();
    int h = surveyProperties.getSiteMainHeight();
    if (im.getWidth() != w || im.getHeight() != h) {
      throw new SiteSaveException(
          "메인 이미지는 "
              + w
              + "×"
              + h
              + " 픽셀이어야 합니다. (현재 "
              + im.getWidth()
              + "×"
              + im.getHeight()
              + ")");
    }
    String ext = guessExt(file.getOriginalFilename(), ".jpg");
    return writeBytes(siteId, "main", ext, raw, mediaRoot);
  }

  private String persistListImage(long siteId, MultipartFile file, Path mediaRoot) throws SiteSaveException {
    byte[] raw;
    try {
      raw = file.getBytes();
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    String ext = guessExt(file.getOriginalFilename(), ".jpg");
    return writeBytes(siteId, "list", ext, raw, mediaRoot);
  }

  /** DB에 들어가는 상대 경로 {@code "{siteId}/main.ext"} */
  private String writeBytes(long siteId, String baseName, String ext, byte[] raw, Path mediaRoot)
      throws SiteSaveException {
    ext = normalizeImageExt(ext);
    Path dir = mediaRoot.resolve(String.valueOf(siteId));
    try {
      Files.createDirectories(dir);
      Path out = dir.resolve(baseName + ext);
      Files.write(out, raw);
    } catch (IOException e) {
      throw new SiteSaveException("이미지 저장에 실패했습니다: " + e.getMessage());
    }
    return siteId + "/" + baseName + ext;
  }

  private static String normalizeImageExt(String ext) {
    String e = ext.toLowerCase(Locale.ROOT);
    if (e.equals(".jpeg")) {
      return ".jpg";
    }
    if (e.equals(".jpg") || e.equals(".png") || e.equals(".webp")) {
      return e;
    }
    return ".jpg";
  }

  private static String guessExt(String original, String def) {
    if (original == null) {
      return def;
    }
    int i = original.lastIndexOf('.');
    if (i < 0) {
      return def;
    }
    return original.substring(i);
  }

  private boolean isSiteNameAvailable(Long orgId, String name, Long excludeId) {
    return siteRepository.findByOrganizationId(orgId).stream()
        .filter(s -> !s.getId().equals(excludeId))
        .map(Site::getName)
        .noneMatch(name::equals);
  }

  private boolean isSiteCodeAvailable(Long orgId, String code, Long excludeId) {
    if (code == null || code.isBlank()) {
      return true;
    }
    String c = code.trim().toLowerCase(Locale.ROOT);
    return siteRepository.findByOrganizationId(orgId).stream()
        .filter(s -> !s.getId().equals(excludeId))
        .map(Site::getSiteCode)
        .filter(Objects::nonNull)
        .map(x -> x.trim().toLowerCase(Locale.ROOT))
        .noneMatch(c::equals);
  }

  private static String normalizeSiteCode(String raw) {
    if (raw == null || raw.isBlank()) {
      return null;
    }
    String t = raw.trim().toLowerCase(Locale.ROOT);
    return SITE_CODE.matcher(t).matches() ? t : null;
  }

  public static class SiteSaveException extends Exception {
    public SiteSaveException(String message) {
      super(message);
    }
  }
}
