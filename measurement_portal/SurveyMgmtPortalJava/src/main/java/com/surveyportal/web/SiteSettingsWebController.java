package com.surveyportal.web;

import com.surveyportal.config.SurveyProperties;
import com.surveyportal.domain.Organization;
import com.surveyportal.domain.Site;
import com.surveyportal.domain.SiteSmsConfig;
import com.surveyportal.domain.SiteSmsRecipient;
import com.surveyportal.repo.OrganizationRepository;
import com.surveyportal.service.SiteSettingsService;
import com.surveyportal.service.SiteSettingsService.SiteSaveException;
import java.util.List;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/site")
public class SiteSettingsWebController {

  private final SiteSettingsService siteSettingsService;
  private final OrganizationRepository organizationRepository;
  private final SurveyProperties surveyProperties;

  public SiteSettingsWebController(
      SiteSettingsService siteSettingsService,
      OrganizationRepository organizationRepository,
      SurveyProperties surveyProperties) {
    this.siteSettingsService = siteSettingsService;
    this.organizationRepository = organizationRepository;
    this.surveyProperties = surveyProperties;
  }

  @GetMapping("/{siteId}/site-settings")
  public String get(
      @PathVariable long siteId,
      @RequestParam(required = false) Long edit,
      Model model) {
    Site site = siteSettingsService.getSiteOrThrow(siteId);
    Organization org = organizationRepository.findById(site.getOrganizationId()).orElse(null);
    SiteSmsConfig sms = siteSettingsService.getOrEmptySmsConfig(siteId);
    List<SiteSmsRecipient> recipients = siteSettingsService.listRecipients(siteId);
    SiteSmsRecipient editing = null;
    if (edit != null) {
      try {
        editing = siteSettingsService.getRecipientOrThrow(siteId, edit);
      } catch (Exception ignored) {
        // 무시 — 잘못된 편집 id
      }
    }
    model.addAttribute("site", site);
    model.addAttribute("orgName", org != null ? org.getName() : "");
    model.addAttribute("sms", sms);
    model.addAttribute("recipients", recipients);
    model.addAttribute("editingRecipient", editing);
    model.addAttribute("siteMainW", surveyProperties.getSiteMainWidth());
    model.addAttribute("siteMainH", surveyProperties.getSiteMainHeight());
    return "site-settings";
  }

  @PostMapping("/{siteId}/site-settings")
  public String post(
      @PathVariable long siteId,
      @RequestParam String _action,
      @RequestParam(required = false) String site_name,
      @RequestParam(required = false) String site_code,
      @RequestParam(required = false) String install_date,
      @RequestParam(required = false) String address,
      @RequestParam(required = false) String site_program,
      @RequestParam(required = false) String memo,
      @RequestParam(required = false) MultipartFile image_main,
      @RequestParam(required = false) MultipartFile image_list,
      @RequestParam(required = false) Boolean sms_enabled,
      @RequestParam(required = false) String sms_message,
      @RequestParam(required = false) String sms_time_from,
      @RequestParam(required = false) String sms_time_to,
      @RequestParam(required = false) Long recipient_id,
      @RequestParam(required = false) Boolean recipient_send,
      @RequestParam(required = false) String recipient_name,
      @RequestParam(required = false) String recipient_phone,
      @RequestParam(required = false) String recipient_job,
      @RequestParam(required = false) String recipient_dept,
      @RequestParam(required = false) String recipient_info,
      @RequestParam(required = false) Long delete_recipient_id,
      RedirectAttributes ra) {
    String redir = "redirect:/site/" + siteId + "/site-settings";
    try {
      switch (_action) {
        case "save_site":
          siteSettingsService.saveSite(
              siteId,
              site_name,
              site_code,
              install_date,
              address,
              site_program,
              memo,
              image_main,
              image_list);
          ra.addFlashAttribute("flashOk", "현장 정보가 저장되었습니다.");
          return redir;
        case "save_sms":
          siteSettingsService.saveSms(
              siteId,
              Boolean.TRUE.equals(sms_enabled),
              sms_message,
              sms_time_from,
              sms_time_to);
          ra.addFlashAttribute("flashOk", "SMS 설정이 저장되었습니다.");
          return redir;
        case "save_recipient":
          siteSettingsService.saveRecipient(
              siteId,
              recipient_id,
              Boolean.TRUE.equals(recipient_send),
              recipient_name,
              recipient_phone,
              recipient_job,
              recipient_dept,
              recipient_info);
          ra.addFlashAttribute("flashOk", "발송 대상자가 저장되었습니다.");
          return redir;
        case "delete_recipient":
          if (delete_recipient_id != null) {
            siteSettingsService.deleteRecipient(siteId, delete_recipient_id);
          }
          ra.addFlashAttribute("flashOk", "삭제되었습니다.");
          return redir;
        default:
          ra.addFlashAttribute("flashError", "알 수 없는 동작입니다.");
          return redir;
      }
    } catch (SiteSaveException ex) {
      ra.addFlashAttribute("flashError", ex.getMessage());
      return redir;
    }
  }
}
