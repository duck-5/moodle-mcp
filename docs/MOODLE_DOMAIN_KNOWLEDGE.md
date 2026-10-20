# Moodle Domain Knowledge & Technical Quirks

This document records essential domain rules, calculation formulas, and platform-specific quirks necessary for building robust tools and AI agents on top of Moodle.

---

## 1. True Deadline Calculation

Moodle assignments store several distinct timestamp fields in Unix epoch seconds:
- `duedate`: The nominal deadline set by the instructor.
- `cutoffdate`: The absolute final deadline after which submissions are permanently locked.
- `extensionduedate`: A personalized extension granted to a specific student (e.g. for military reserve duty, illness, or accommodations).

### The Formula
$$\text{True Deadline} = \max(\text{duedate}, \text{cutoffdate}, \text{extensionduedate})$$

### Crucial Implementation Constraints
1. **Exclude `0` Values**: An epoch value of `0` in Moodle signifies that the date is **unset** (not January 1, 1970). Never include `0` in the maximum calculation.
2. **All Zeros Fallback**: If `duedate`, `cutoffdate`, and `extensionduedate` are all `0`, the assignment has **no deadline**.
3. **Timezone Handling**: Moodle timestamps are in UTC epoch seconds. Display dates should be rendered in the local campus timezone (`Asia/Jerusalem` / Israel Standard Time UTC+2, Daylight Time UTC+3).

### Status Classification Rules
- **`Submitted`**: If `lastattempt.submission.status == 'submitted'`.
- **`Not submitted (Overdue)`**: If status is not submitted AND `true_deadline > 0` AND `true_deadline < current_time`.
- **`Assigned (Pending)`**: If status is not submitted AND (`true_deadline >= current_time` OR `true_deadline == 0`).

---

## 2. Zoom LTI Pro Discovery & Deduplication

In modern university Moodle courses, Zoom meetings are managed through multiple mechanisms:

1. **LTI Pro Activities (`modname == 'lti'`)**:
   - The instructor creates an LTI activity titled "Zoom" or "מפגש מקוון".
   - Launching this activity sends an OAuth 1.0 signed POST to `https://applications.zoom.us/lti/rich`.
   - The LTI application exposes two JSON endpoints:
     - Upcoming meetings: `/api/v1/lti/rich/meeting/upComing/COURSE/all?page=1&total=0`
     - Past meetings: `/api/v1/lti/rich/meeting/previous/COURSE/all?page=1&total=0`
2. **Direct URL Modules (`modname == 'url'`)**:
   - The instructor inserts a direct hyperlink to a meeting (`https://tau-ac-il.zoom.us/j/{id}?pwd={hash}`).
3. **Embedded HTML Links (`modname == 'label' | 'page'`)**:
   - Hyperlinks embedded inside course announcements or section descriptions.

### Quirks & Normalization

#### Non-Scheduled Meeting Timestamps
Zoom LTI Pro rooms configured with "No Fixed Time" (`type == 3`), Personal Meeting ID rooms (`type == 4`), or instant rooms (`type == 1`) return their **creation timestamp** in the `startTime` field. A meeting created 6 months ago on a Tuesday at 14:23:47 will report `14:23:47` as its start time.
- **Rule**: Only trust `startTime` if the room has scheduled recurring instances or is aligned to standard lecture boundaries.

#### Recurring Meeting Deduplication
A course may have 14 weekly entries for the same lecture room.
- **Rule**: Collapse recurring entries with the same `meetingNumber` into a single active representative:
  - If a meeting is currently live (between start time and start time + 2 hours), display it with high priority.
  - Otherwise, display the nearest upcoming date.

---

## 3. Panopto Video Recording Discovery

Tel Aviv University records classroom lectures using Panopto (`tau.cloud.panopto.eu`):

1. **LTI Tool Launch**:
   - Moodle course sections include an LTI link to the Panopto course folder.
2. **Direct RSS / Podcast Feed**:
   - Panopto exposes an RSS feed of course recordings:
     ```
     https://tau.cloud.panopto.eu/Panopto/Podcast/Podcast.ashx?courseId={course_guid}
     ```
   - Each item in the RSS feed represents a lecture or recitation (*tirgul*) with video title, duration, recording date, and direct streaming/download URL.
3. **Hebrew Classification**:
   - Videos containing `"תרגול"` or `"תרגיל"` in the title are classified as Recitations.
   - Videos containing `"הרצאה"` or `"שיעור"` are classified as Lectures.

---

## 4. Windows Unicode & Encoding Quirks

When running Python scripts on Windows:
1. **Console Codepage (`cp1252`)**: By default, Windows PowerShell and `cmd.exe` use `cp1252` encoding. Attempting to print Hebrew characters from Moodle course titles (e.g. `מבני נתונים`) raises `UnicodeEncodeError: 'charmap' codec can't encode characters`.
2. **Remediation**:
   Always enforce UTF-8 on `sys.stdout` and `sys.stderr` at the very entry point of the CLI application:
   ```python
   import sys
   if sys.platform == "win32":
       sys.stdout.reconfigure(encoding="utf-8")
       sys.stderr.reconfigure(encoding="utf-8")
   ```
