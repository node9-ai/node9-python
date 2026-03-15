import { GoogleGenerativeAI } from "@google/generative-ai";
import { Octokit } from "@octokit/rest";

const prNumber = parseInt(process.env.PR_NUMBER);
const githubToken = process.env.GITHUB_TOKEN;
const [repoOwner, repoName] = (process.env.GITHUB_REPOSITORY || "").split("/");

const octokit = new Octokit({ auth: githubToken });

async function runReview() {
  try {
    console.log(`Fetching diff for PR #${prNumber}...`);
    const { data: prDiff } = await octokit.pulls.get({
      owner: repoOwner,
      repo: repoName,
      pull_number: prNumber,
      mediaType: { format: "diff" },
    });

    if (!prDiff || prDiff.trim().length === 0) {
      console.log("Empty diff, skipping review.");
      return;
    }

    const prompt = `You are a senior Python engineer reviewing a pull request for the Node9 Python SDK.
Node9 is an execution security library — a @protect decorator that intercepts AI agent tool calls and asks for human approval before running them.

Review the following git diff and provide concise, actionable feedback. Focus on:
- Correctness and edge cases
- Security issues (this is a security library — be strict)
- API design and usability for developers integrating with LangChain, CrewAI, etc.
- Test coverage gaps
- Anything that could break the daemon HTTP communication

If the changes look good with no issues, say so briefly.
Do NOT rewrite the code. Just review it.
Keep your review under 400 words.

## Git Diff:
${prDiff}`;

    console.log("Sending diff to Gemini for review...");
    const genAI = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY);
    const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
    const result = await model.generateContent([prompt]);
    const review = result.response.text();

    console.log("Posting review comment...");
    await octokit.issues.createComment({
      owner: repoOwner,
      repo: repoName,
      issue_number: prNumber,
      body: `## 🤖 Gemini Code Review\n\n${review}\n\n---\n*Automated review by Gemini 2.5 Flash*`,
    });

    console.log("Review posted successfully.");
  } catch (error) {
    console.error("Error:", error.message);
    process.exit(1);
  }
}

runReview();
