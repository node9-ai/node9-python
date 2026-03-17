import Anthropic from "@anthropic-ai/sdk";
import { Octokit } from "@octokit/rest";

const prNumber = parseInt(process.env.PR_NUMBER);
const githubToken = process.env.GITHUB_TOKEN;
const repo = process.env.GITHUB_REPOSITORY || "";
const [repoOwner, repoName] = repo.split("/");

if (!prNumber || !githubToken || !repoOwner || !repoName || !process.env.ANTHROPIC_API_KEY) {
  console.error("Missing required environment variables.");
  process.exit(1);
}

const MAX_DIFF_CHARS = 20000;
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

    const wasTruncated = prDiff.length > MAX_DIFF_CHARS;
    const truncatedDiff = wasTruncated
      ? prDiff.slice(0, MAX_DIFF_CHARS) + "\n\n... [diff truncated]"
      : prDiff;

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
Keep your review under 800 words.

## Git Diff:
${truncatedDiff}`;

    console.log("Sending diff to Claude for review...");
    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const message = await client.messages.create({
      model: "claude-sonnet-4-6",
      max_tokens: 2048,
      messages: [{ role: "user", content: prompt }],
    });

    const review = message.content[0].text;

    console.log("Posting review comment...");
    await octokit.issues.createComment({
      owner: repoOwner,
      repo: repoName,
      issue_number: prNumber,
      body: `## 🤖 Claude Code Review\n\n${review}${wasTruncated ? "\n\n> ⚠️ **Note:** This diff exceeded 20,000 characters and was truncated. The review above covers only the first portion of the changes." : ""}\n\n---\n*Automated review by Claude Sonnet*`,
    });

    console.log("Review posted successfully.");
  } catch (error) {
    console.error("Error:", error.message);
    process.exit(1);
  }
}

runReview();
