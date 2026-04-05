const fs = require("fs");
const path = require("path");
const Module = require("module");

const vaultRoot = path.resolve(__dirname, "../../..");
const notices = [];

function normalizePath(input) {
  return input.replace(/\\/g, "/").replace(/\/+/g, "/").replace(/^\.\//, "");
}

function parseFrontmatterAndTags(text) {
  const cache = {};

  if (text.startsWith("---\n")) {
    const end = text.indexOf("\n---", 4);
    if (end !== -1) {
      const yaml = text.slice(4, end).split("\n");
      const frontmatter = {};
      let currentListKey = null;

      for (const rawLine of yaml) {
        const line = rawLine.trimEnd();
        const keyMatch = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
        if (keyMatch) {
          const [, key, value] = keyMatch;
          if (!value) {
            frontmatter[key] = [];
            currentListKey = key;
          } else {
            frontmatter[key] = value.replace(/^"(.*)"$/, "$1");
            currentListKey = null;
          }
          continue;
        }

        const listMatch = line.match(/^\s*-\s+(.*)$/);
        if (listMatch && currentListKey) {
          frontmatter[currentListKey].push(listMatch[1].replace(/^"(.*)"$/, "$1"));
        }
      }

      cache.frontmatter = frontmatter;
    }
  }

  const inlineTags = [...text.matchAll(/(^|\s)#([A-Za-z0-9/_-]+)/g)].map((match) => ({ tag: `#${match[2]}` }));
  if (inlineTags.length) {
    cache.tags = inlineTags;
  }

  return cache;
}

class MockNotice {
  constructor(message) {
    notices.push(message);
  }
}

class MockPlugin {
  constructor(app) {
    this.app = app;
    this.commands = [];
    this.settingTabs = [];
    this._data = {};
  }

  addCommand(command) {
    this.commands.push(command);
  }

  addSettingTab(tab) {
    this.settingTabs.push(tab);
  }

  async loadData() {
    return this._data;
  }

  async saveData(data) {
    this._data = data;
  }
}

class MockPluginSettingTab {
  constructor(app, plugin) {
    this.app = app;
    this.plugin = plugin;
    this.containerEl = { empty() {} };
  }
}

class MockSetting {
  setName() {
    return this;
  }

  setDesc() {
    return this;
  }

  addText(callback) {
    callback({
      setPlaceholder() {
        return this;
      },
      setValue() {
        return this;
      },
      onChange() {
        return this;
      }
    });
    return this;
  }

  addToggle(callback) {
    callback({
      setValue() {
        return this;
      },
      onChange() {
        return this;
      }
    });
    return this;
  }
}

const originalLoad = Module._load;
Module._load = function patchedLoad(request, parent, isMain) {
  if (request === "obsidian") {
    return {
      Notice: MockNotice,
      Plugin: MockPlugin,
      PluginSettingTab: MockPluginSettingTab,
      Setting: MockSetting,
      normalizePath
    };
  }

  return originalLoad(request, parent, isMain);
};

function getMarkdownFiles(dir, relative = "") {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const relPath = relative ? `${relative}/${entry.name}` : entry.name;
    const absPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      files.push(...getMarkdownFiles(absPath, relPath));
      continue;
    }

    if (!entry.name.endsWith(".md")) {
      continue;
    }

    const stat = fs.statSync(absPath);
    files.push({
      path: normalizePath(relPath),
      basename: path.basename(entry.name, ".md"),
      stat: { mtime: stat.mtimeMs }
    });
  }

  return files;
}

function makeApp() {
  const markdownFiles = getMarkdownFiles(vaultRoot);

  return {
    vault: {
      getMarkdownFiles() {
        return getMarkdownFiles(vaultRoot);
      },
      async cachedRead(file) {
        return fs.readFileSync(path.join(vaultRoot, file.path), "utf8");
      },
      getAbstractFileByPath(filePath) {
        const absPath = path.join(vaultRoot, filePath);
        if (!fs.existsSync(absPath)) {
          return null;
        }

        const stat = fs.statSync(absPath);
        if (stat.isDirectory()) {
          return { path: filePath, children: [] };
        }

        return {
          path: normalizePath(filePath),
          basename: path.basename(filePath, ".md"),
          stat: { mtime: stat.mtimeMs }
        };
      },
      async create(filePath, contents) {
        fs.writeFileSync(path.join(vaultRoot, filePath), contents, "utf8");
      },
      async createFolder(folderPath) {
        fs.mkdirSync(path.join(vaultRoot, folderPath), { recursive: false });
      }
    },
    metadataCache: {
      getFileCache(file) {
        const text = fs.readFileSync(path.join(vaultRoot, file.path), "utf8");
        return parseFrontmatterAndTags(text);
      }
    },
    workspace: {
      openedFile: null,
      getLeaf() {
        return {
          openFile: async (file) => {
            this.openedFile = file.path;
          }
        };
      }
    }
  };
}

async function main() {
  const fixtureDir = path.join(vaultRoot, "Ops Brief Test");
  const generatedFixtureFiles = [
    {
      name: "Incident Example.md",
      body: [
        "---",
        "tags:",
        "  - incident",
        "---",
        "# API latency incident",
        "",
        "Increased 95th percentile latency after the rollout.",
        "",
        "- [ ] Confirm whether autoscaling thresholds need tuning.",
        "- [ ] Add timeline notes to the postmortem."
      ].join("\n")
    },
    {
      name: "Meeting Example.md",
      body: [
        "---",
        "tags:",
        "  - meeting",
        "---",
        "# Platform weekly sync",
        "",
        "Reviewed rollout health, CI noise, and follow-up actions for next week."
      ].join("\n")
    }
  ];

  fs.mkdirSync(fixtureDir, { recursive: true });
  for (const fixture of generatedFixtureFiles) {
    fs.writeFileSync(path.join(fixtureDir, fixture.name), fixture.body, "utf8");
  }

  const pluginModule = require("./main.js");
  const PluginClass = pluginModule.default || pluginModule;
  const app = makeApp();
  const plugin = new PluginClass(app);
  let latest = null;
  const operationsDir = path.join(vaultRoot, "Operations");
  const existingOpsBriefs = fs.existsSync(operationsDir)
    ? new Set(fs.readdirSync(operationsDir).filter((name) => name.startsWith("Ops Brief ")))
    : new Set();

  try {
    await plugin.onload();

    const command = plugin.commands.find((item) => item.id === "generate-ops-brief");
    if (!command) {
      throw new Error("Generate ops brief command was not registered.");
    }

    await command.callback();

    const generated = fs
      .readdirSync(operationsDir)
      .filter((name) => name.startsWith("Ops Brief "))
      .filter((name) => !existingOpsBriefs.has(name))
      .sort()
      .map((name) => path.join(operationsDir, name));

    if (!generated.length) {
      throw new Error("No ops brief note was created.");
    }

    latest = generated[generated.length - 1];
    const body = fs.readFileSync(latest, "utf8");

    console.log(JSON.stringify({
      generated: path.relative(vaultRoot, latest),
      notices,
      preview: body.split("\n").slice(0, 32)
    }, null, 2));
  } finally {
    for (const fixture of generatedFixtureFiles) {
      const fixturePath = path.join(fixtureDir, fixture.name);
      if (fs.existsSync(fixturePath)) {
        fs.unlinkSync(fixturePath);
      }
    }

    if (fs.existsSync(fixtureDir)) {
      fs.rmdirSync(fixtureDir);
    }

    if (latest && fs.existsSync(latest)) {
      fs.unlinkSync(latest);
    }
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
