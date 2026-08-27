import { chromium } from "playwright";
import { execSync } from "node:child_process";

const email = `stageb_${Date.now()}@example.com`;
const password = "supersecret123";

const browser = await chromium.launch();
const page = await browser.newPage();
const consoleErrors = [];
page.on("console", (msg) => {
  if (msg.type() === "error") consoleErrors.push(msg.text());
});
page.on("pageerror", (err) => consoleErrors.push(String(err)));

await page.goto("http://localhost:5173");
await page.waitForTimeout(500);

console.log("--- initial page ---");
console.log((await page.locator("body").innerText()).slice(0, 400));

await page.fill('input[type="email"]', email);
await page.fill('input[type="password"]', password);
const termsCheckbox = page.locator('input[type="checkbox"]');
if (await termsCheckbox.count()) {
  await termsCheckbox.first().check();
}
await page.getByRole("button", { name: /sign up|register|create account/i }).click();
await page.waitForTimeout(1000);
console.log("--- after register submit ---");
console.log((await page.locator("body").innerText()).slice(0, 400));

// Bypass email verification for this local dev-only smoke test — flip
// is_verified directly in the dev sqlite DB (verification tokens are
// stored hashed, so they can't be reconstructed from the DB).
execSync(
  `sqlite3 /Users/choonhakunjaroonwatthana/Desktop/aladdin2/backend/aladdin2.db "UPDATE users SET is_verified=1 WHERE email='${email}';"`,
);
console.log("verified user in DB");

await page.goto("http://localhost:5173");
await page.waitForTimeout(500);
await page.fill('input[type="email"]', email);
await page.fill('input[type="password"]', password);
await page.getByRole("button", { name: /log in|sign in/i }).click();
await page.waitForTimeout(1500);
console.log("--- after login ---");
console.log((await page.locator("body").innerText()).slice(0, 500));

await page.screenshot({ path: "/tmp/stageb_01_dashboard.png", fullPage: true });

// Navigate to Research Lab
await page.getByRole("button", { name: "Research Lab" }).click();
await page.waitForTimeout(500);
console.log("url after clicking Research Lab:", page.url());
console.log((await page.locator("body").innerText()).slice(0, 500));
await page.screenshot({ path: "/tmp/stageb_02_research_lab.png", fullPage: true });

await browser.close();
console.log("console errors:", JSON.stringify(consoleErrors, null, 2));
