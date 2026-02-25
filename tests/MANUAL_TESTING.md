# Manual Testing Guide for GitHub Workflow

This document provides instructions for manually testing the GitHub workflow features of AI News Radar.

## Prerequisites

- A GitHub repository with the AI News Radar code
- GitHub Actions enabled
- Optional: Telegram Bot Token and Chat ID for testing notifications

## GitHub Workflow Testing

### 1. Concurrency Control Testing

**Objective**: Verify that only one workflow runs at a time when multiple triggers occur.

**Steps**:
1. Make two commits in quick succession
2. Observe the Actions tab in your GitHub repository
3. Check that only one workflow completes while the other is cancelled

**Expected Result**:
- One workflow run completes successfully
- Second workflow is marked as "Cancelled" with reason "concurrency"
- No duplicate commits are created

**Verification**:
```bash
# Check commit history
git log --oneline -10

# Verify only one "chore: update ai news snapshot" commit per time period
```

### 2. Dependency Caching Testing

**Objective**: Verify that pip dependencies are cached for faster subsequent runs.

**Steps**:
1. Clear any existing cache manually (optional)
2. Run the workflow once
3. Check the Actions logs for cache-related messages
4. Run the workflow again
5. Compare the "Install dependencies" step duration

**Expected Result**:
- First run: Shows "Cache not found" and installs dependencies from scratch
- Second run: Shows "Cache restored from key" and completes faster
- Cache hit/miss is logged in the workflow output

**Verification**:
```bash
# Check cache in GitHub repository
# Navigate to: Repository -> Actions -> Caches
```

### 3. Conditional Commit Testing (No Changes)

**Objective**: Verify that no commit is created when there are no data changes.

**Steps**:
1. Run the workflow manually with workflow_dispatch
2. Immediately run it again before any external data changes
3. Check the Actions tab and commit history

**Expected Result**:
- First workflow run completes and commits data changes
- Second workflow completes with message "No changes to commit"
- Second workflow exits with code 0
- No new commits appear after the second run

**Verification**:
```bash
# Count commits after two runs
git log --oneline --grep="chore: update ai news snapshot" -5

# Should see only one commit, not two
```

### 4. Conditional Commit Testing (With Changes)

**Objective**: Verify that commit is created when there are data changes.

**Steps**:
1. Modify one of the data files (e.g., add a test item)
2. Run the workflow manually
3. Check the Actions tab and commit history

**Expected Result**:
- Workflow completes successfully
- Commit is created with message "chore: update ai news snapshot"
- Commit includes modified data files

**Verification**:
```bash
# Check the latest commit
git log -1 --stat

# Should show changes to data files
```

### 5. Telegram Notification Testing

**Prerequisites**:
- Create a Telegram bot via @BotFather
- Get your bot token
- Get your chat ID (send a message to @userinfobot)
- Add secrets to GitHub repository:
  - `TELEGRAM_BOT_TOKEN`: Your bot token
  - `TELEGRAM_CHAT_ID`: Your chat ID

**Steps**:
1. Add the Telegram secrets to your repository
2. Run the workflow manually
3. Check your Telegram for a notification

**Expected Result**:
- You receive a notification about the workflow run
- Notification includes status (success/failure)
- For failures, includes error details

**Verification**:
- Check Telegram chat for the notification message
- Verify the message contains relevant information

**Testing Success Notification**:
1. Ensure workflow runs successfully
2. Check for success message in Telegram

**Testing Failure Notification**:
1. Temporarily modify the workflow to fail (e.g., invalid command)
2. Run the workflow
3. Check for failure notification with error details
4. Restore the workflow

### 6. Environment Variable Configuration Testing

**Objective**: Verify different DB_TYPE configurations work correctly.

**Testing File Storage (Default)**:
1. Ensure no DB_TYPE environment variable is set in workflow
2. Run the workflow
3. Check that data files are created in the data/ directory

**Testing SQLite Storage**:
1. Add to workflow (or repository secrets):
   ```yaml
   env:
     DB_TYPE: sqlite
     DB_FILE: /path/to/database.db
   ```
2. Run the workflow
3. Verify database file is created
4. Check that data is stored in the database

**Testing MySQL Storage** (with mock/testing):
1. Set up a test MySQL database
2. Add to workflow:
   ```yaml
   env:
     DB_TYPE: mysql
     MYSQL_HOST: test-host
     MYSQL_PORT: 3306
     MYSQL_USER: test-user
     MYSQL_PASSWORD: test-password
     MYSQL_DATABASE: test-db
   ```
3. Run the workflow
4. Verify connection to MySQL is attempted
5. Check logs for connection status

**Testing PostgreSQL Storage** (with mock/testing):
1. Set up a test PostgreSQL database
2. Add to workflow:
   ```yaml
   env:
     DB_TYPE: postgresql
     POSTGRES_HOST: test-host
     POSTGRES_PORT: 5432
     POSTGRES_USER: test-user
     POSTGRES_PASSWORD: test-password
     POSTGRES_DATABASE: test-db
   ```
3. Run the workflow
4. Verify connection to PostgreSQL is attempted
5. Check logs for connection status

**Testing Missing Credentials**:
1. Set DB_TYPE to mysql or postgresql
2. Omit required credentials (e.g., MYSQL_PASSWORD)
3. Run the workflow
4. Check that it falls back to file storage gracefully

**Expected Result**:
- File storage: Works without any DB configuration
- SQLite: Creates database file
- MySQL/PostgreSQL: Attempts connection, falls back on failure
- Missing credentials: Graceful error handling with fallback

### 7. OPML RSS Testing

**Objective**: Verify OPML RSS processing works correctly.

**Testing with OPML**:
1. Create a test OPML file:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <opml version="2.0">
   <body>
   <outline text="Test Feed" title="Test Feed" xmlUrl="https://test.example.com/feed.xml" />
   </body>
   </opml>
   ```
2. Add as GitHub Secret `FOLLOW_OPML_B64` (base64 encoded)
3. Run the workflow
4. Check that RSS items are included in the output

**Testing without OPML**:
1. Remove or unset FOLLOW_OPML_B64 secret
2. Run the workflow
3. Check that workflow completes without OPML data
4. Verify source-status.json shows OPML as disabled

### 8. Workflow Schedule Testing

**Objective**: Verify the scheduled workflow runs correctly.

**Steps**:
1. Check the workflow file for the schedule:
   ```yaml
   schedule:
     - cron: "*/30 * * * *"
   ```
2. Monitor the Actions tab over time
3. Verify workflow runs every 30 minutes

**Expected Result**:
- Workflow runs automatically at the scheduled time
- Each run completes successfully
- Data is updated at each run

### 9. Workflow Trigger Testing

**Testing Manual Trigger (workflow_dispatch)**:
1. Go to Actions tab in your repository
2. Select "Update AI News Snapshot" workflow
3. Click "Run workflow" button
4. Verify workflow starts and completes

**Testing Push Trigger**:
1. Push a commit to the main branch
2. Verify workflow is triggered
3. Check that it runs after the push

### 10. Output File Verification

**Objective**: Verify all expected output files are created.

**Steps**:
1. After a successful workflow run
2. Check the repository for these files:
   - `data/latest-24h.json`
   - `data/archive.json`
   - `data/source-status.json`
   - `data/waytoagi-7d.json`
   - `data/title-zh-cache.json`

**Expected Result**:
- All files exist
- Files contain valid JSON
- Files are committed to the repository

**Verification**:
```bash
# Check files exist
ls -la data/*.json

# Validate JSON
for f in data/*.json; do
  python -m json.tool "$f" > /dev/null && echo "$f: Valid" || echo "$f: Invalid"
done
```

## Debugging Failed Tests

### Check Workflow Logs

1. Go to Actions tab
2. Click on the failed workflow run
3. Click on each step to see detailed logs
4. Look for error messages and stack traces

### Common Issues

**Issue**: Workflow is cancelled due to concurrency
- **Solution**: This is expected behavior, not an error

**Issue**: Cache not found
- **Solution**: First run after cache expiration; subsequent runs should use cache

**Issue**: No changes to commit
- **Solution**: Expected behavior when data hasn't changed

**Issue**: Telegram notification not received
- **Solution**: Check:
  - Bot token is correct
  - Chat ID is correct
  - Bot is started (send /start to your bot)
  - Secrets are properly configured

**Issue**: Database connection failed
- **Solution**: Check:
  - Credentials are correct
  - Database is accessible from GitHub Actions
  - Firewall rules allow connection

## Cleanup After Testing

1. Remove test secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - Test database credentials

2. Delete test data commits:
   ```bash
   git reset --hard HEAD~N  # Where N is number of test commits
   git push --force
   ```

3. Clear test caches in Actions > Caches

## Test Report Template

```
Date: [Date]
Tester: [Name]
Environment: [Description]

### Concurrency Control
- Status: [Pass/Fail]
- Notes: [Any observations]

### Dependency Caching
- Status: [Pass/Fail]
- First run duration: [Time]
- Second run duration: [Time]
- Improvement: [Percentage]

### Conditional Commits
- No Changes: [Pass/Fail]
- With Changes: [Pass/Fail]
- Notes: [Any observations]

### Telegram Notifications
- Success Notification: [Pass/Fail]
- Failure Notification: [Pass/Fail]
- Notes: [Any observations]

### DB Configuration
- File Storage: [Pass/Fail]
- SQLite: [Pass/Fail]
- MySQL (Mock): [Pass/Fail]
- PostgreSQL (Mock): [Pass/Fail]
- Fallback Behavior: [Pass/Fail]

### OPML Processing
- With OPML: [Pass/Fail]
- Without OPML: [Pass/Fail]
- Notes: [Any observations]

### Output Files
- latest-24h.json: [Pass/Fail]
- archive.json: [Pass/Fail]
- source-status.json: [Pass/Fail]
- waytoagi-7d.json: [Pass/Fail]
- title-zh-cache.json: [Pass/Fail]

### Overall Result
- Summary: [Overall Pass/Fail]
- Issues Found: [List any issues]
- Recommendations: [Any recommendations for improvement]
```

## Additional Resources

- GitHub Actions Documentation: https://docs.github.com/en/actions
- Telegram Bot API: https://core.telegram.org/bots/api
- Cron Expression Tester: https://crontab.guru
