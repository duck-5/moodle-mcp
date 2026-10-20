# Moodle Web Service REST API Reference

This document provides a comprehensive technical reference for the Moodle REST Web Service API, specifically based on Moodle 3.x–4.x and Tel Aviv University's Moodle instance (`moodle.tau.ac.il`).

---

## 1. Request Architecture & Transport

All Moodle REST API calls interact with a single gateway endpoint:

```http
POST /webservice/rest/server.php
Host: moodle.tau.ac.il
```

### Core Query / Form Parameters

Every request must include the following parameters (sent either as URL query string parameters or `application/x-www-form-urlencoded` POST fields):

| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `wstoken` | string | **Yes** | 32-character hexadecimal Web Service token (e.g. `24584e27f9191d848149e6f8510a7479`). |
| `wsfunction` | string | **Yes** | The Web Service function name (e.g. `core_webservice_get_site_info`). |
| `moodlewsrestformat` | string | **Yes** | Must be set to `json`. Without this, Moodle defaults to returning XML. |

> [!IMPORTANT]
> **HTTP 200 on Errors**: Moodle's REST gateway returns HTTP status `200 OK` even when an API call fails completely. The client must inspect the JSON response body. If the response contains `{"exception": "...", "message": "...", "errorcode": "..."}`, the call has failed and must be handled as an error.

### Common Error Codes

| `errorcode` | Meaning | Remediation |
| :--- | :--- | :--- |
| `invalidtoken` | The Web Service token has expired, been revoked, or does not exist. | Trigger re-authentication via SSO to obtain a fresh token. |
| `accessexception` | The token lacks permission for this web service function. | Verify the token was generated for `Moodle mobile web service` rather than an auxiliary service. |
| `servicenotavailable` | The service is disabled on the Moodle site. | Fall back to session cookie / web scraping. |
| `invalidrecord` | The requested entity (course ID, assignment ID) does not exist or user lacks access. | Verify IDs and user enrollment. |

---

## 2. Core Endpoints Reference

### 1. User & Site Info: `core_webservice_get_site_info`

Fetches metadata about the authenticated user and the Moodle installation.

- **Function:** `core_webservice_get_site_info`
- **Method:** `GET` or `POST`
- **Parameters:** None (inferred from `wstoken`).
- **Response Structure:**

```json
{
  "sitename": "TAU Moodle 2025-2026",
  "username": "student_username",
  "firstname": "ישראל",
  "lastname": "ישראלי",
  "fullname": "ישראל ישראלי",
  "lang": "he",
  "userid": 123456,
  "userpictureurl": "https://moodle.tau.ac.il/pluginfile.php/...",
  "functions": [
    { "name": "core_enrol_get_users_courses", "version": 2022112800 },
    { "name": "mod_assign_get_assignments", "version": 2022112800 }
  ],
  "downloadfiles": 1,
  "uploadfiles": 1,
  "release": "4.1.2 (Build: 20230313)",
  "version": "2022112802.00"
}
```

---

### 2. Enrolled Courses: `core_enrol_get_users_courses`

Retrieves all courses in which the user is enrolled.

- **Function:** `core_enrol_get_users_courses`
- **Method:** `GET` or `POST`
- **Parameters:**
  - `userid` (int, required): The Moodle internal ID of the student (obtained from `get_site_info`).
- **Response Structure (Array of Courses):**

```json
[
  {
    "id": 12345,
    "shortname": "0368111801-2025-1",
    "fullname": "מבני נתונים (0368111801) - תשפ\"ה סמסטר א'",
    "displayname": "מבני נתונים (0368111801) - תשפ\"ה סמסטר א'",
    "idnumber": "0368111801-2025-1",
    "visible": 1,
    "summary": "<p>תיאור הקורס ומטרותיו...</p>",
    "summaryformat": 1,
    "format": "topics",
    "showgrades": true,
    "lang": "he",
    "enablecompletion": true,
    "completionhascriteria": true,
    "completionusertracked": true,
    "category": 42,
    "progress": 75.0,
    "startdate": 1729458000,
    "enddate": 1738360800
  }
]
```

#### Academic Metadata Parsing

At Tel Aviv University, the course `shortname` or `idnumber` follows the format:
`{course_code}-{academic_year}-{semester}` (e.g. `0368111801-2025-1`):
- `course_code`: `0368111801` (8-10 digit course code).
- `academic_year`: `2025` (representing academic year 2024-2025 / תשפ"ה).
- `semester`: `1` (Semester A / סמסטר א'), `2` (Semester B / סמסטר ב'), `3` (Summer / קיץ).

---

### 3. Course Contents: `core_course_get_contents`

Retrieves the complete hierarchical section-by-section breakdown of course materials, including lecture notes, lab assignments, syllabus, links, and activities.

- **Function:** `core_course_get_contents`
- **Method:** `GET` or `POST`
- **Parameters:**
  - `courseid` (int, required): Moodle internal course ID.
  - `options[0][name]=excludemodules&options[0][value]=0` (optional)
  - `options[1][name]=excludecontents&options[1][value]=0` (optional)
- **Response Structure (Array of Sections):**

```json
[
  {
    "id": 89012,
    "name": "שבוע 1 - מבוא וניתוח סיבוכיות",
    "visible": 1,
    "summary": "<p>בחלק זה נלמד על סימוני O גדול וחישוב סיבוכיות זמן ריצה.</p>",
    "summaryformat": 1,
    "section": 1,
    "modules": [
      {
        "id": 34567,
        "name": "מצגת שבוע 1 - סיבוכיות",
        "instance": 123,
        "modname": "resource",
        "modplural": "Files",
        "modicon": "https://moodle.tau.ac.il/theme/image.php/...",
        "indent": 0,
        "visible": 1,
        "contents": [
          {
            "type": "file",
            "filename": "Lecture01.pdf",
            "filepath": "/",
            "filesize": 2458920,
            "fileurl": "https://moodle.tau.ac.il/webservice/pluginfile.php/12345/mod_resource/content/1/Lecture01.pdf",
            "timecreated": 1729458000,
            "timemodified": 1729459000,
            "sortorder": 1,
            "mimetype": "application/pdf",
            "isexternalfile": false
          }
        ]
      },
      {
        "id": 34568,
        "name": "מפגש זום שבועי",
        "instance": 456,
        "modname": "lti",
        "modplural": "External tools",
        "url": "https://moodle.tau.ac.il/mod/lti/view.php?id=34568"
      }
    ]
  }
]
```

#### Module Types (`modname`)

- `resource`: Static file (PDF, PPTX, DOCX, ZIP, MP4, code).
- `assign`: Moodle assignment.
- `url`: External hyperlink.
- `folder`: Collection of downloadable files.
- `page`: In-line HTML page.
- `label`: In-line HTML snippet or announcement.
- `quiz`: Online test / quiz.
- `forum`: Discussion board.
- `lti`: External LTI 1.1 / 1.3 tool (Zoom, Panopto, Gradescope).

---

### 4. Assignments Catalog: `mod_assign_get_assignments`

Retrieves all assignment metadata across specified courses in a single request.

- **Function:** `mod_assign_get_assignments`
- **Method:** `GET` or `POST`
- **Parameters:**
  - `courseids[0]` (int, optional): First course ID.
  - `courseids[1]` (int, optional): Second course ID.
  *(If omitted, returns assignments across all enrolled courses).*
- **Response Structure:**

```json
{
  "courses": [
    {
      "id": 12345,
      "fullname": "מבני נתונים (0368111801)",
      "shortname": "0368111801-2025-1",
      "timemodified": 1729458000,
      "assignments": [
        {
          "id": 7890,
          "cmid": 34570,
          "course": 12345,
          "name": "תרגיל רטוב 1 - עצי חיפוש בינאריים",
          "nosubmissions": 0,
          "submissiondrafts": 0,
          "sendnotifications": 0,
          "sendlatenotifications": 0,
          "duedate": 1731276000,
          "allowsubmissionsfromdate": 1729458000,
          "grade": 100,
          "timemodified": 1729458000,
          "completionsubmit": 1,
          "cutoffdate": 1731880800,
          "gradingduedate": 0,
          "intro": "<p>הנחיות לתרגיל: יש לממש ב-C++ עץ חיפוש בינארי מאוזן...</p>",
          "introformat": 1,
          "introattachments": [
            {
              "filename": "hw1_specification.pdf",
              "filesize": 348120,
              "fileurl": "https://moodle.tau.ac.il/webservice/pluginfile.php/...",
              "mimetype": "application/pdf"
            }
          ]
        }
      ]
    }
  ]
}
```

---

### 5. Submission Status & True Deadlines: `mod_assign_get_submission_status`

Retrieves the submission status, attempt history, grading feedback, and personal extension for a specific assignment.

- **Function:** `mod_assign_get_submission_status`
- **Method:** `GET` or `POST`
- **Parameters:**
  - `assignid` (int, required): Moodle assignment ID.
  - `userid` (int, optional): Target student user ID. Defaults to current user.
- **Response Structure:**

```json
{
  "lastattempt": {
    "submission": {
      "id": 45678,
      "userid": 123456,
      "attemptnumber": 0,
      "timecreated": 1730000000,
      "timemodified": 1731000000,
      "status": "submitted",
      "groupid": 0,
      "plugins": [
        {
          "type": "file",
          "name": "File submissions",
          "fileareas": [
            {
              "area": "submission_files",
              "files": [
                {
                  "filename": "solution.zip",
                  "filepath": "/",
                  "filesize": 1048576,
                  "fileurl": "https://moodle.tau.ac.il/webservice/pluginfile.php/...",
                  "timemodified": 1731000000,
                  "mimetype": "application/zip"
                }
              ]
            }
          ]
        },
        {
          "type": "onlinetext",
          "name": "Online text",
          "editorfields": [
            {
              "name": "onlinetext",
              "text": "<p>הערה לבודק: מצורפת הרצה לדוגמה...</p>",
              "format": 1
            }
          ]
        }
      ]
    },
    "submissiongroupmemberswhoneedtosubmit": [],
    "submissionsenabled": true,
    "locked": false,
    "graded": true,
    "canedit": false,
    "cansubmit": false,
    "extensionduedate": 1732000000
  },
  "feedback": {
    "grade": {
      "id": 98765,
      "assignment": 7890,
      "userid": 123456,
      "attemptnumber": 0,
      "timecreated": 1731500000,
      "timemodified": 1731600000,
      "grader": 54321,
      "grade": "95.00000"
    },
    "gradefordisplay": "95.00 / 100.00",
    "plugins": [
      {
        "type": "comments",
        "name": "Feedback comments",
        "editorfields": [
          {
            "name": "comments",
            "text": "עבודה מצוינת! הורדו 5 נקודות על מקרה קצה בריצה.",
            "format": 1
          }
        ]
      }
    ]
  }
}
```

---

### 6. User Grades: `gradereport_user_get_grade_items`

Retrieves detailed grade items, weighting, feedback, and course total from the Moodle gradebook.

- **Function:** `gradereport_user_get_grade_items`
- **Method:** `GET` or `POST`
- **Parameters:**
  - `courseid` (int, required): Moodle internal course ID.
  - `userid` (int, required): Student internal ID.
- **Response Structure:**

```json
{
  "usergrades": [
    {
      "courseid": 12345,
      "userid": 123456,
      "userfullname": "ישראל ישראלי",
      "maxdepth": 2,
      "gradeitems": [
        {
          "id": 6789,
          "itemname": "תרגיל רטוב 1 - עצי חיפוש בינאריים",
          "itemtype": "mod",
          "itemmodule": "assign",
          "iteminstance": 7890,
          "itemnumber": 0,
          "idnumber": "",
          "categoryid": 12,
          "outcomeid": null,
          "scaleid": null,
          "locked": false,
          "cmid": 34570,
          "weightraw": 0.15,
          "weightformatted": "15.00 %",
          "grademin": 0.0,
          "grademax": 100.0,
          "graderaw": 95.0,
          "gradeformatted": "95.00",
          "percentageformatted": "95.00 %",
          "feedback": "<p>עבודה מעולה</p>",
          "feedbackformat": 1,
          "gradedategraded": 1731600000,
          "gradedatesubmitted": 1731000000
        },
        {
          "id": 6790,
          "itemname": "ציון סופי בקורס",
          "itemtype": "course",
          "itemmodule": null,
          "iteminstance": 12345,
          "grademin": 0.0,
          "grademax": 100.0,
          "graderaw": 92.5,
          "gradeformatted": "92.50"
        }
      ]
    }
  ]
}
```

---

### 7. File Upload: `core_files_upload` & `/webservice/upload.php`

Moodle supports two mechanisms to upload submission attachments:

#### Option A: Direct Multipart to `/webservice/upload.php` (Recommended)

- **URL:** `https://moodle.tau.ac.il/webservice/upload.php`
- **Method:** `POST` (`multipart/form-data`)
- **Headers:** `Authorization: Bearer <TOKEN>` or `token=<TOKEN>` in query string.
- **Form Fields:**
  - `token` (string): Web Service token.
  - `filearea` (string): Usually `'draft'`.
  - `itemid` (int): Draft item ID (`0` to generate a new container, or existing `itemid`).
  - `file` (binary): The file content.
  - `filename` (string): The destination file name.
- **Response:**

```json
[
  {
    "component": "user",
    "contextid": 12345,
    "userid": 123456,
    "filearea": "draft",
    "filename": "hw1_solution.zip",
    "filepath": "/",
    "itemid": 987654321,
    "license": "allrightsreserved",
    "author": "ישראל ישראלי",
    "filesize": 512000,
    "timecreated": 1730000000,
    "url": "https://moodle.tau.ac.il/draftfile.php/..."
  }
]
```

#### Option B: Base64 JSON Upload via `core_files_upload`

- **Function:** `core_files_upload`
- **Parameters:**
  - `component`: `'user'`
  - `filearea`: `'draft'`
  - `itemid`: `0`
  - `filepath`: `'/'`
  - `filename`: `'solution.py'`
  - `filecontent`: `'<BASE64_ENCODED_STRING>'`
  - `contextid`: (optional)

---

### 8. Save Submission Draft: `mod_assign_save_submission`

Attaches the draft file item or online text to the student's submission.

- **Function:** `mod_assign_save_submission`
- **Parameters:**
  - `assignmentid` (int, required): Assignment ID.
  - `plugindata[files_filemanager]` (int): The `itemid` returned by the upload API.
  - `plugindata[onlinetext_editor][text]` (string, optional): Online text submission body.
  - `plugindata[onlinetext_editor][format]` (int, optional): `1` (HTML).
  - `plugindata[onlinetext_editor][itemid]` (int, optional): Editor draft itemid.

---

### 9. Submit for Final Grading: `mod_assign_submit_for_grading`

Transitions an assignment from `draft` status to `submitted` status for teacher grading.

- **Function:** `mod_assign_submit_for_grading`
- **Parameters:**
  - `assignmentid` (int, required): Assignment ID.
  - `acceptsubmissionstatement` (int, required): `1` (Confirms academic integrity statement).

---

### 10. LTI Tool Launch Data: `mod_lti_get_tool_launch_data`

Retrieves OAuth 1.0 signed launch parameters for embedded external tools (Zoom Pro, Panopto).

- **Function:** `mod_lti_get_tool_launch_data`
- **Parameters:**
  - `toolid` (int, required): Internal LTI tool ID or course module ID.
- **Response Structure:**

```json
{
  "endpoint": "https://applications.zoom.us/lti/rich",
  "parameters": [
    { "name": "oauth_version", "value": "1.0" },
    { "name": "oauth_consumer_key", "value": "..." },
    { "name": "oauth_signature", "value": "..." },
    { "name": "custom_canvas_course_id", "value": "12345" }
  ]
}
```

---

## 3. Authenticated File Download Mechanics

Files hosted on Moodle (e.g. lecture PDFs, assignment handouts) are served via `pluginfile.php`.

### URL Formats

```
https://moodle.tau.ac.il/webservice/pluginfile.php/{contextid}/{component}/{filearea}/{itemid}/{filename}
https://moodle.tau.ac.il/pluginfile.php/{contextid}/{component}/{filearea}/{itemid}/{filename}
```

### Authentication Rules

1. **When using `wstoken`**:
   Append `?token={wstoken}` to the file URL:
   ```
   https://moodle.tau.ac.il/webservice/pluginfile.php/12345/mod_resource/content/1/lecture.pdf?token=24584e27f9191d848149e6f8510a7479
   ```
2. **When using browser session cookies (`MoodleSession`)**:
   Send HTTP `GET` with header `Cookie: MoodleSession=...` directly to `pluginfile.php`. Do NOT append `?token=...` when using session cookies.
