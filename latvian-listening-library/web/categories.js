(function () {
  // ---------------------------------------------------------------------------
  // Category Definitions — Practical real-life situations for A2 learners
  // ---------------------------------------------------------------------------
  var CATEGORIES = [
    {
      id: 'doctor',
      icon: '🏥',
      title: 'Doctor visit',
      titleLv: 'Pie ārsta',
      description: 'Medical appointments, symptoms, prescriptions',
      examTopics: ['health']
    },
    {
      id: 'pharmacy',
      icon: '💊',
      title: 'Pharmacy',
      titleLv: ' Aptiekā',
      description: 'Medicine, prescriptions, health products',
      examTopics: ['health', 'services']
    },
    {
      id: 'school',
      icon: '🏫',
      title: 'School or kindergarten',
      titleLv: 'Skola vai bērnudārzs',
      description: 'Parent-teacher meetings, school events',
      examTopics: ['family', 'free time']
    },
    {
      id: 'grocery',
      icon: '🛒',
      title: 'Grocery shopping',
      titleLv: 'Pārtikas veikals',
      description: 'Shopping, prices, quantities, preferences',
      examTopics: ['shopping']
    },
    {
      id: 'cafe',
      icon: '☕',
      title: 'Café or restaurant',
      titleLv: 'Kafejnīca vai restorāns',
      description: 'Ordering, menus, paying, preferences',
      examTopics: ['shopping', 'free time']
    },
    {
      id: 'transport',
      icon: '🚌',
      title: 'Public transport',
      titleLv: 'Sabiedriskais transports',
      description: 'Bus, tram, train tickets, directions',
      examTopics: ['transport']
    },
    {
      id: 'work',
      icon: '💼',
      title: 'Work conversation',
      titleLv: 'Darba saruna',
      description: 'Jobs, schedules, workplace interactions',
      examTopics: ['work']
    },
    {
      id: 'government',
      icon: '🏛️',
      title: 'Government office',
      titleLv: 'Valsts iestāde',
      description: 'Residency, permits, bureaucratic procedures',
      examTopics: ['services']
    },
    {
      id: 'bank',
      icon: '🏦',
      title: 'Bank and services',
      titleLv: 'Banka un pakalpojumi',
      description: 'Banking, post office, utilities',
      examTopics: ['services']
    },
    {
      id: 'housing',
      icon: '🏠',
      title: 'Housing and landlord',
      titleLv: 'Dzīvoklis un īpašnieks',
      description: 'Renting, repairs, household matters',
      examTopics: ['services']
    },
    {
      id: 'weather',
      icon: '🌤️',
      title: 'Weather and small talk',
      titleLv: 'Laiks un neliels sarunu',
      description: 'Weather, casual conversations',
      examTopics: ['free time']
    },
    {
      id: 'family',
      icon: '👨‍👩‍👧',
      title: 'Family and daily routine',
      titleLv: 'Gimene un ikdiena',
      description: 'Family activities, daily life',
      examTopics: ['family', 'free time']
    },
    {
      id: 'bureaucracy',
      icon: '📋',
      title: 'Latvian bureaucracy',
      titleLv: 'Latvijas birokrātija',
      description: 'Official documents, offices, procedures',
      examTopics: ['services']
    },
    {
      id: 'uncategorized',
      icon: '📁',
      title: 'Uncategorized',
      titleLv: 'Neklasificēts',
      description: 'Lessons not yet categorized',
      examTopics: []
    }
  ];

  // Category to exam topic mapping
  var EXAM_TOPICS = {
    shopping: { icon: '🛍️', label: 'Shopping' },
    transport: { icon: '🚆', label: 'Transport' },
    health: { icon: '🏥', label: 'Health' },
    services: { icon: '🏢', label: 'Services' },
    work: { icon: '💼', label: 'Work' },
    family: { icon: '👨‍👩‍👧', label: 'Family' },
    freeTime: { icon: '🎮', label: 'Free time' }
  };

  // Mapping from item ID prefixes to categories (simple heuristic)
  // This can be extended with more specific mappings
  var CATEGORY_MAPPINGS = {
    // A1 items - general greetings and basics
    'A1-29ac14e2': 'family',   // 1.nodalja - nice to meet you
    'A1-bb3b9178': 'family',   // greetings
    'A1-c8bb435d': 'family',   // greetings
    
    // More mappings can be added as needed
  };

  // ---------------------------------------------------------------------------
  // Category API
  // ---------------------------------------------------------------------------
  var CategoryManager = {
    getCategories: function () {
      return CATEGORIES.filter(function (c) { return c.id !== 'uncategorized'; });
    },

    getCategoryById: function (id) {
      return CATEGORIES.find(function (c) { return c.id === id; });
    },

    getExamTopics: function () {
      return EXAM_TOPICS;
    },

    // Assign category to an item based on heuristics
    getCategoryForItem: function (item) {
      // First check explicit mapping
      if (CATEGORY_MAPPINGS[item.id]) {
        return CATEGORY_MAPPINGS[item.id];
      }
      
      // Default to uncategorized
      return 'uncategorized';
    },

    // Get all categories with item counts
    getCategoriesWithCounts: function (catalog) {
      var counts = {};
      CATEGORIES.forEach(function (c) { counts[c.id] = 0; });
      
      catalog.forEach(function (item) {
        var catId = CategoryManager.getCategoryForItem(item);
        counts[catId] = (counts[catId] || 0) + 1;
      });
      
      return CATEGORIES.map(function (c) {
        return {
          id: c.id,
          icon: c.icon,
          title: c.title,
          titleLv: c.titleLv,
          description: c.description,
          examTopics: c.examTopics,
          count: counts[c.id] || 0
        };
      });
    },

    // Filter catalog by category
    filterByCategory: function (catalog, categoryId) {
      if (!categoryId || categoryId === 'all') {
        return catalog.slice();
      }
      return catalog.filter(function (item) {
        return CategoryManager.getCategoryForItem(item) === categoryId;
      });
    },

    // Get exam topic labels for an item
    getExamTopicsForItem: function (item) {
      var categoryId = CategoryManager.getCategoryForItem(item);
      var category = CategoryManager.getCategoryById(categoryId);
      if (!category) return [];
      return category.examTopics.map(function (topic) {
        return EXAM_TOPICS[topic] || { label: topic };
      });
    }
  };

  // Export to global scope
  if (typeof window !== 'undefined') {
    window.CategoryManager = CategoryManager;
    window.CATEGORIES = CATEGORIES;
    window.EXAM_TOPICS = EXAM_TOPICS;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CategoryManager: CategoryManager, CATEGORIES: CATEGORIES, EXAM_TOPICS: EXAM_TOPICS };
  }
})();