import readline from 'readline';

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

const question = (query) => new Promise(resolve => rl.question(query, resolve));

// --- SSO Cookie Jar & Fetch Helpers ---
class CookieJar {
  constructor() { this.store = {}; }
  ingest(raw) {
    if (!raw) return;
    const normalized = raw.replace(/\r?\n/g, ', ');
    const parts = normalized.split(/,\s*(?=[a-zA-Z0-9_\-!#$%&'*+.^`|~]+=)/);
    for (const part of parts) {
      const nameVal = part.split(';')[0].trim();
      const eq = nameVal.indexOf('=');
      if (eq > 0) {
        const name = nameVal.slice(0, eq).trim();
        const value = nameVal.slice(eq + 1).trim();
        if (name) this.store[name] = value;
      }
    }
  }
  header() {
    return Object.entries(this.store).map(([k, v]) => `${k}=${v}`).join('; ');
  }
}

const _realFetch = global.fetch;

async function mfetch(jar, url, init = {}) {
  const cookieStr = jar.header();
  const headers = { ...init.headers };
  if (cookieStr) headers['Cookie'] = cookieStr;
  const fetchFn = global._originalFetch || _realFetch;
  const res = await fetchFn(url, { ...init, headers, redirect: 'manual' });
  jar.ingest(res.headers.get('set-cookie'));
  return res;
}

async function mfetchFollow(jar, url, init = {}, maxRedirects = 15) {
  let currentUrl = url;
  let currentInit = { ...init };
  for (let i = 0; i <= maxRedirects; i++) {
    const res = await mfetch(jar, currentUrl, currentInit);
    const status = res.status;
    if (status >= 300 && status < 400) {
      const loc = res.headers.get('location') ?? res.headers.get('Location') ?? '';
      if (!loc) return { response: res, finalUrl: currentUrl };
      let nextUrl = loc;
      try { nextUrl = loc.startsWith('http') ? loc : new URL(loc, currentUrl).href; } catch (e) {}
      if (nextUrl.startsWith('moodlemobile://') || nextUrl.startsWith('moodleapp://')) {
        return { response: res, finalUrl: nextUrl };
      }
      if (status === 301 || status === 302 || status === 303) currentInit = {};
      currentUrl = nextUrl;
      continue;
    }
    return { response: res, finalUrl: currentUrl };
  }
  throw new Error('Too many redirects');
}

function decodeHTMLEntities(text) {
  return text.replace(/&quot;/g, '"').replace(/&#x3d;/gi, '=').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}

async function loginTauSso(username, idNumber, password) {
  const jar = new CookieJar();
  const { response: res1, finalUrl: urlAfterLogin } = await mfetchFollow(jar, 'https://moodle.tau.ac.il/login/index.php');
  
  let baseUrl = 'https://moodle.tau.ac.il';
  let ssoUrl = urlAfterLogin;

  if (urlAfterLogin.includes('/auth/saml2/login.php')) {
    baseUrl = urlAfterLogin.split('/auth')[0];
    const samlRes = await mfetchFollow(jar, urlAfterLogin);
    ssoUrl = samlRes.finalUrl;
  }

  if (!ssoUrl.includes('nidp.tau.ac.il')) throw new Error(`Unexpected SSO redirect: ${ssoUrl}`);

  let samlInitRes = await mfetchFollow(jar, ssoUrl);
  const html1 = await samlInitRes.response.text();
  const formMatch1 = html1.match(/<form[^>]+action=["']([^"']+)["']/i);
  if (formMatch1) {
    const action = formMatch1[1];
    ssoUrl = action.startsWith('http') ? action : new URL(action, 'https://nidp.tau.ac.il').href;
    const params = new URLSearchParams();
    const inputs = [...html1.matchAll(/<input[^>]+name=["']([^"']+)["'][^>]+value=["']([^"']+)["']/gi)];
    inputs.forEach(m => params.append(decodeHTMLEntities(m[1]), decodeHTMLEntities(m[2])));
    await mfetch(jar, ssoUrl, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: params.toString() });
  }

  await mfetch(jar, ssoUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'option=credential&initiateLoginSequence=true&isAjax=true',
  });

  const credBody = `option=credential&isAjax=true&Ecom_User_ID=${encodeURIComponent(username)}&Ecom_User_Pid=${encodeURIComponent(idNumber)}&Ecom_Password=${encodeURIComponent(password)}`;
  const credRes = await mfetch(jar, ssoUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: credBody,
  });
  const credText = await credRes.text();
  if (credText.replace(/\s/g, '').includes('"isError":true')) {
    throw new Error('Wrong username, ID number, or password during SSO');
  }

  const samlRes = await mfetch(jar, ssoUrl);
  const html2 = await samlRes.text();
  const actionMatch = html2.match(/<form[^>]+action=["']([^"']+)["']/i);
  const samlValMatch = html2.match(/<input[^>]+name=["']SAMLResponse["'][^>]+value=["']([^"']+)["']/i);
  
  if (!actionMatch || !samlValMatch) throw new Error('Failed to parse SAML assertion');
  
  const actionUrl = decodeHTMLEntities(actionMatch[1]);
  const samlResponse = decodeHTMLEntities(samlValMatch[1]);
  
  const bodyParams = new URLSearchParams();
  bodyParams.append('SAMLResponse', samlResponse);
  
  const { response: moodleRes } = await mfetchFollow(jar, actionUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: bodyParams.toString(),
  });

  const moodleHtml = await moodleRes.text();
  const sesskeyMatch = moodleHtml.match(/"sesskey":"([^"]+)"/);
  if (!sesskeyMatch) throw new Error('Failed to extract sesskey from Moodle after SSO login');
  
  const useridMatch = moodleHtml.match(/"userid"\s*:\s*(\d+)/);
  if (useridMatch && parseInt(useridMatch[1], 10) <= 1) {
    throw new Error('SSO login resulted in a Guest session. Please check your username, ID, and password.');
  }
  
  const sesskey = sesskeyMatch[1];
  
  // Scrape mobile token
  const manageUrl = `${baseUrl}/user/managetoken.php`;
  const manageRes = await mfetchFollow(jar, manageUrl);
  const manageHtml = await manageRes.response.text();
  
  const tokenMatch = manageHtml.match(/(?:Moodle mobile web service|moodle_mobile_app|Mobile)[^]*?action=resetwstoken(?:&amp;|&)tokenid=(\d+)/i);
  if (!tokenMatch) throw new Error('Could not find existing Moodle Mobile Web Service token to reset');
  
  const resetParams = new URLSearchParams();
  resetParams.append('tokenid', tokenMatch[1]);
  resetParams.append('action', 'resetwstoken');
  resetParams.append('confirm', '1');
  resetParams.append('sesskey', sesskey);
  
  const resetRes = await mfetchFollow(jar, manageUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: resetParams.toString(),
  });
  
  const resetHtml = await resetRes.response.text();
  const finalTokenMatch = resetHtml.match(/id="copytoclipboardtoken"[^>]*>([^<]+)<\/div>/i);
  if (finalTokenMatch) return { token: finalTokenMatch[1].trim(), jar, sesskey };
  
  throw new Error('SSO login successful but failed to extract the wstoken from user/managetoken.php');
}

async function callMoodleWs(token, wsfunction, params = {}) {
  const url = new URL('https://moodle.tau.ac.il/webservice/rest/server.php');
  url.searchParams.set('wstoken', token);
  url.searchParams.set('wsfunction', wsfunction);
  url.searchParams.set('moodlewsrestformat', 'json');
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, String(v));
  }
  const res = await fetch(url.toString(), { method: 'POST' });
  const data = await res.json();
  if (data && data.exception) {
    throw new Error(`Moodle API Error [${data.errorcode}]: ${data.message}`);
  }
  return data;
}

async function main() {
  console.log("=== Node.js Moodle API Live Test Script ===\n");
  
  let token = process.env.MOODLE_TOKEN;
  
  if (!token) {
    const envUsername = process.env.MOODLE_TESTING_USERNAME || process.env.MOODLE_USERNAME;
    const envPassword = process.env.MOODLE_TESTING_PASSWORD || process.env.MOODLE_PASSWORD;
    const envId = process.env.MOODLE_TESTING_ID || process.env.MOODLE_ID_NUMBER;
    
    if (envUsername && envPassword && envId) {
      console.log(`[AUTH] Found SSO credentials for: ${envUsername}. Logging in via TAU SSO...`);
      try {
        const result = await loginTauSso(envUsername, envId, envPassword);
        token = result.token;
        console.log(`[AUTH] Successfully logged in! Extracted wstoken: ${token.slice(0, 6)}...${token.slice(-6)}\n`);
      } catch (err) {
        console.error("[AUTH] Failed to login via SSO:", err.message);
        process.exit(1);
      }
    } else {
      console.error("[AUTH] Please provide MOODLE_USERNAME and MOODLE_PASSWORD in environment or .env.");
      process.exit(1);
    }
  }

  try {
    console.log("--- 1. Testing core_webservice_get_site_info ---");
    const siteInfo = await callMoodleWs(token, 'core_webservice_get_site_info');
    console.log(`[SUCCESS] Connected as: ${siteInfo.fullname} (ID: ${siteInfo.userid})`);
    console.log(`[SITE] ${siteInfo.sitename} | Release: ${siteInfo.release}`);

    console.log("\n--- 2. Testing core_enrol_get_users_courses ---");
    const courses = await callMoodleWs(token, 'core_enrol_get_users_courses', { userid: siteInfo.userid });
    console.log(`[SUCCESS] Found ${courses.length} enrolled courses.`);
    courses.slice(0, 5).forEach(c => console.log(`  - [${c.id}] ${c.fullname}`));

    console.log("\n--- 3. Testing mod_assign_get_assignments ---");
    const assignData = await callMoodleWs(token, 'mod_assign_get_assignments');
    const allAssigns = (assignData.courses || []).flatMap(c => c.assignments || []);
    console.log(`[SUCCESS] Found ${allAssigns.length} assignments across all courses.`);
    
    console.log("\nAll checks passed successfully!");
  } catch (err) {
    console.error("\n[FATAL ERROR] Test aborted:", err.message);
  } finally {
    rl.close();
  }
}

main();
