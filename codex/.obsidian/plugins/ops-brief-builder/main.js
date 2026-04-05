const { Notice, Plugin, PluginSettingTab, Setting, normalizePath } = require("obsidian");

const DEFAULT_SETTINGS = {
  outputFolder: "Operations",
  lookbackDays: 7,
  meetingTags: "meeting,standup,retro",
  incidentTags: "incident,postmortem,outage",
  followUpTags: "action-item,todo,followup",
  includeUncategorizedWithTasks: true
};

class OpsBriefBuilderPlugin extends Plugin {
  async onload() {
    await this.loadSettings();

    this.addCommand({
      id: "generate-ops-brief",
      name: "Generate ops brief",
      callback: async () => {
        await this.generateOpsBrief();
      }
    });

    this.addSettingTab(new OpsBriefSettingTab(this.app, this));
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  async generateOpsBrief() {
    const since = Date.now() - this.settings.lookbackDays * 24 * 60 * 60 * 1000;
    const files = this.app.vault
      .getMarkdownFiles()
      .filter((file) => file.stat.mtime >= since)
      .filter((file) => this.shouldConsiderFile(file));

    if (!files.length) {
      new Notice("No recent notes found for the ops brief.");
      return;
    }

    const buckets = {
      incidents: [],
      meetings: [],
      followUps: [],
      uncategorized: []
    };

    for (const file of files) {
      const cache = this.app.metadataCache.getFileCache(file) || {};
      const tags = this.extractTags(cache);
      const text = await this.app.vault.cachedRead(file);
      const excerpt = this.buildExcerpt(file, cache, text);
      const entry = {
        file,
        excerpt,
        tasks: this.extractTasks(text)
      };

      if (this.matchesAnyTag(tags, this.settings.incidentTags)) {
        buckets.incidents.push(entry);
      } else if (this.matchesAnyTag(tags, this.settings.meetingTags)) {
        buckets.meetings.push(entry);
      } else if (this.matchesAnyTag(tags, this.settings.followUpTags)) {
        buckets.followUps.push(entry);
      } else if (this.settings.includeUncategorizedWithTasks && entry.tasks.length) {
        buckets.uncategorized.push(entry);
      } else {
        continue;
      }
    }

    const matchingCount =
      buckets.incidents.length + buckets.meetings.length + buckets.followUps.length + buckets.uncategorized.length;

    if (!matchingCount) {
      new Notice("No recent tagged notes or open tasks matched the ops brief filters.");
      return;
    }

    const notePath = await this.createUniqueBriefPath();
    await this.ensureFolder(this.settings.outputFolder);

    const contents = this.renderBrief(notePath, buckets);
    await this.app.vault.create(notePath, contents);

    const created = this.app.vault.getAbstractFileByPath(notePath);
    if (created) {
      await this.app.workspace.getLeaf(true).openFile(created);
    }

    new Notice(`Created ops brief: ${notePath}`);
  }

  extractTags(cache) {
    const frontmatterTags = cache.frontmatter?.tags || [];
    const inlineTags = (cache.tags || []).map((tag) => tag.tag.replace(/^#/, ""));

    const normalizedFrontmatter = Array.isArray(frontmatterTags)
      ? frontmatterTags
      : String(frontmatterTags)
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean);

    return [...normalizedFrontmatter, ...inlineTags].map((tag) => tag.replace(/^#/, "").toLowerCase());
  }

  matchesAnyTag(noteTags, configuredTags) {
    const configured = configuredTags
      .split(",")
      .map((tag) => tag.trim().toLowerCase())
      .filter(Boolean);

    return configured.some((tag) => noteTags.includes(tag));
  }

  shouldConsiderFile(file) {
    if (file.path.startsWith(".obsidian/")) {
      return false;
    }

    if (file.path.startsWith(`${this.settings.outputFolder}/`)) {
      return false;
    }

    return true;
  }

  buildExcerpt(file, cache, text) {
    const body = text.startsWith("---\n")
      ? text.replace(/^---\n[\s\S]*?\n---\n?/, "")
      : text;

    const lines = body
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#") && !line.startsWith(">") && !line.startsWith("```"));

    const firstParagraph = lines.find((line) => !line.startsWith("- [ ]") && !line.startsWith("- [x]"));
    const summary = firstParagraph || "No summary line found.";
    const modified = new Date(file.stat.mtime).toISOString().slice(0, 10);
    const title = cache.frontmatter?.title || file.basename;

    return { title, summary, modified };
  }

  extractTasks(text) {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.startsWith("- [ ]"))
      .slice(0, 5);
  }

  async createUniqueBriefPath() {
    const date = new Date().toISOString().slice(0, 10);
    const base = normalizePath(`${this.settings.outputFolder}/Ops Brief ${date}.md`);

    if (!this.app.vault.getAbstractFileByPath(base)) {
      return base;
    }

    let counter = 2;
    while (true) {
      const candidate = normalizePath(`${this.settings.outputFolder}/Ops Brief ${date} (${counter}).md`);
      if (!this.app.vault.getAbstractFileByPath(candidate)) {
        return candidate;
      }
      counter += 1;
    }
  }

  async ensureFolder(path) {
    const normalized = normalizePath(path);
    if (this.app.vault.getAbstractFileByPath(normalized)) {
      return;
    }

    const segments = normalized.split("/");
    let current = "";

    for (const segment of segments) {
      current = current ? `${current}/${segment}` : segment;
      if (!this.app.vault.getAbstractFileByPath(current)) {
        await this.app.vault.createFolder(current);
      }
    }
  }

  renderBrief(notePath, buckets) {
    const generatedAt = new Date().toISOString();
    const allSources = [
      ...buckets.incidents,
      ...buckets.meetings,
      ...buckets.followUps,
      ...buckets.uncategorized
    ];

    return [
      "---",
      `title: "${this.basenameFromPath(notePath).replace(/"/g, '\\"')}"`,
      "tags:",
      "  - ops-brief",
      `generated: "${generatedAt}"`,
      `lookback_days: ${this.settings.lookbackDays}`,
      "---",
      "",
      "# Operations Brief",
      "",
      `Generated from ${allSources.length} recent notes.`,
      "",
      "## Snapshot",
      `- Incidents: ${buckets.incidents.length}`,
      `- Meetings: ${buckets.meetings.length}`,
      `- Follow-ups: ${buckets.followUps.length}`,
      `- Uncategorized: ${buckets.uncategorized.length}`,
      "",
      "## Incidents",
      this.renderEntries(buckets.incidents),
      "",
      "## Meetings",
      this.renderEntries(buckets.meetings),
      "",
      "## Follow-ups",
      this.renderEntries(buckets.followUps, true),
      "",
      "## Uncategorized",
      this.renderEntries(buckets.uncategorized),
      "",
      "## Sources",
      allSources.length ? allSources.map((entry) => `- [[${entry.file.path}]]`).join("\n") : "- None"
    ].join("\n");
  }

  renderEntries(entries, includeTasks = false) {
    if (!entries.length) {
      return "- None";
    }

    return entries
      .map((entry) => {
        const lines = [
          `- [[${entry.file.path}|${entry.excerpt.title}]] (${entry.excerpt.modified}): ${entry.excerpt.summary}`
        ];

        if (includeTasks && entry.tasks.length) {
          lines.push(...entry.tasks.map((task) => `  ${task}`));
        }

        return lines.join("\n");
      })
      .join("\n");
  }

  basenameFromPath(path) {
    const parts = path.split("/");
    return parts[parts.length - 1].replace(/\.md$/, "");
  }
}

class OpsBriefSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("Output folder")
      .setDesc("Folder for generated ops briefs.")
      .addText((text) =>
        text.setPlaceholder("Operations").setValue(this.plugin.settings.outputFolder).onChange(async (value) => {
          this.plugin.settings.outputFolder = value.trim() || DEFAULT_SETTINGS.outputFolder;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Lookback days")
      .setDesc("Only notes modified within this window are included.")
      .addText((text) =>
        text.setPlaceholder("7").setValue(String(this.plugin.settings.lookbackDays)).onChange(async (value) => {
          const parsed = Number.parseInt(value, 10);
          this.plugin.settings.lookbackDays = Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_SETTINGS.lookbackDays;
          await this.plugin.saveSettings();
        })
      );

    new Setting(containerEl)
      .setName("Meeting tags")
      .setDesc("Comma-separated tags used for meeting notes.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.meetingTags)
          .setValue(this.plugin.settings.meetingTags)
          .onChange(async (value) => {
            this.plugin.settings.meetingTags = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Incident tags")
      .setDesc("Comma-separated tags used for incident notes.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.incidentTags)
          .setValue(this.plugin.settings.incidentTags)
          .onChange(async (value) => {
            this.plugin.settings.incidentTags = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Follow-up tags")
      .setDesc("Comma-separated tags used for notes with open work.")
      .addText((text) =>
        text
          .setPlaceholder(DEFAULT_SETTINGS.followUpTags)
          .setValue(this.plugin.settings.followUpTags)
          .onChange(async (value) => {
            this.plugin.settings.followUpTags = value;
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Include uncategorized task notes")
      .setDesc("Include recent notes with open checkbox tasks even when they do not match configured tags.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.includeUncategorizedWithTasks).onChange(async (value) => {
          this.plugin.settings.includeUncategorizedWithTasks = value;
          await this.plugin.saveSettings();
        })
      );
  }
}

module.exports = OpsBriefBuilderPlugin;
module.exports.default = OpsBriefBuilderPlugin;
