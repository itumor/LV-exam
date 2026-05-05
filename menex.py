#!/usr/bin/env python3
"""
MenEx: Web Menu Extractor
Automatically extracts menus from webpages using DOM weight analysis.
"""

import asyncio
import argparse
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, NavigableString, Tag
import requests
from typing import Optional


class MenuExtractor:
    """Extract menus from webpages using DOM weight analysis."""

    MENU_TAG_NAMES = {'nav', 'menu', 'ul', 'ol', 'div', 'section', 'aside', 'header'}
    MENU_LINK_TAGS = {'a', 'button'}
    MENU_CLASS_PATTERNS = [
        r'nav', r'menu', r'header', r'footer', r'sidebar', r'navigation',
        r'topbar', r'main-nav', r'site-nav', r'primary', r'secondary',
        r'main-menu', r'submenu', r'breadcrumb'
    ]
    IGNORE_IDS = {'content', 'main', 'article', 'footer', 'sidebar'}

    def __init__(self, html: str, base_url: str = ""):
        self.soup = BeautifulSoup(html, 'html.parser')
        self.base_url = base_url
        self.weights: dict[int, float] = {}

    def extract(self) -> list[dict]:
        """Main extraction method - returns list of potential menus."""
        self._calculate_weights()
        candidates = self._find_menu_candidates()
        return self._extract_menus(candidates)

    def _calculate_weights(self) -> None:
        """Calculate weight for each DOM node based on menu heuristics."""
        for i, tag in enumerate(self.soup.find_all(True)):
            weight = 0.0

            tag_name = tag.name.lower()
            class_attr = (tag.get('class') or [])
            class_str = ' '.join(class_attr).lower() if class_attr else ''
            id_attr = (tag.get('id') or '').lower()
            role = (tag.get('role') or '').lower()

            if tag_name in self.MENU_TAG_NAMES:
                weight += 5.0

            for pattern in self.MENU_CLASS_PATTERNS:
                if re.search(pattern, class_str) or re.search(pattern, id_attr):
                    weight += 10.0
                    break

            if role in ('navigation', 'menu', 'menubar'):
                weight += 15.0

            links = tag.find_all(self.MENU_LINK_TAGS)
            if len(links) >= 2:
                weight += min(len(links) * 0.5, 10)

            if tag_name == 'ul' and not class_attr and not id_attr:
                if tag.parent and tag.parent.name in self.MENU_TAG_NAMES:
                    weight += 8.0

            if id_attr in self.IGNORE_IDS:
                weight -= 20.0

            aria_label = tag.get('aria-label') or tag.get('aria-labelledby')
            if aria_label:
                weight += 5.0

            has_nested_lists = tag.find_all(['ul', 'ol'])
            if len(has_nested_lists) >= 2:
                weight += 3.0

            self.weights[id(tag)] = weight

    def _find_menu_candidates(self) -> list[Tag]:
        """Find top weighted elements likely to be menus."""
        sorted_tags = sorted(
            [(tag, self.weights.get(id(tag), 0)) for tag in self.soup.find_all(True)],
            key=lambda x: x[1],
            reverse=True
        )

        candidates = []
        max_weight = max(w for t, w in sorted_tags) if sorted_tags else 0

        for tag, weight in sorted_tags[:50]:
            if weight <= 0:
                continue
            if weight >= max_weight * 0.8:
                candidates.append(tag)
                continue

            parent_has_candidate = False
            for ancestor in tag.parents:
                if ancestor in candidates:
                    parent_has_candidate = True
                    break
            if parent_has_candidate and weight < 15:
                continue

            candidates.append(tag)

        return candidates

    def _extract_menus(self, candidates: list[Tag]) -> list[dict]:
        """Extract structured menu data from candidates."""
        menus = []
        seen_paths = set()

        for tag in candidates:
            menu_data = self._extract_single_menu(tag)
            if menu_data:
                path = menu_data['path']
                if path not in seen_paths:
                    seen_paths.add(path)
                    menus.append(menu_data)

        return menus

    def _extract_single_menu(self, tag: Tag) -> Optional[dict]:
        """Extract a single menu structure."""
        links = tag.find_all(self.MENU_LINK_TAGS)
        if len(links) < 2:
            return None

        items = []
        seen_text = set()

        for link in links:
            href = link.get('href', '')
            text = self._get_link_text(link)
            if not text:
                continue
            text_lower = text.lower().strip()
            if text_lower in seen_text:
                continue
            if href and (href.startswith('#') or href.startswith('javascript:')):
                continue

            seen_text.add(text_lower)
            full_href = urljoin(self.base_url, href) if href else ""
            items.append({
                'text': text.strip(),
                'href': full_href,
                'classes': ' '.join(link.get('class', []))
            })

        if len(items) < 2:
            return None

        path = self._get_dom_path(tag)

        return {
            'tag': tag.name,
            'id': tag.get('id', ''),
            'classes': ' '.join(tag.get('class', [])),
            'role': tag.get('role', ''),
            'aria_label': tag.get('aria-label', ''),
            'path': path,
            'items': items,
            'item_count': len(items),
            'weight': self.weights.get(id(tag), 0),
            'html': str(tag)
        }

    def _get_link_text(self, link: Tag) -> str:
        """Get clean text from a link."""
        parts = []
        for child in link.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    parts.append(text)
        return ' '.join(parts) if parts else link.get_text(strip=True)

    def _get_dom_path(self, tag: Tag) -> str:
        """Generate DOM path for the tag."""
        parts = []
        for parent in tag.parents:
            if parent.name in ('html', 'body'):
                break
            name = parent.name
            parent_id = parent.get('id')
            parent_class = (parent.get('class') or [''])[0] if parent.get('class') else ''
            if parent_id:
                parts.append(f"{name}#{parent_id}")
            elif parent_class:
                parts.append(f"{name}.{parent_class}")
            else:
                parts.append(name)
        return '/'.join(reversed(parts))


class MenuExtractorCLI:
    """Command-line interface for MenEx."""

    def __init__(self):
        self.args = self._parse_args()

    def _parse_args(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description='MenEx: Web Menu Extractor',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog='''
Examples:
  python3 menex.py https://example.com
  python3 menex.py https://example.com --output menu.html
  python3 menex.py https://example.com --format json --min-items 3
  python3 menex.py --file index.html --format text
            '''
        )
        parser.add_argument('url', nargs='?', help='URL to extract menu from')
        parser.add_argument('-f', '--file', help='Read from local HTML file')
        parser.add_argument('-o', '--output', help='Save extracted menu to file')
        parser.add_argument('-m', '--min-items', type=int, default=2,
                           help='Minimum number of links (default: 2)')
        parser.add_argument('-r', '--raw', action='store_true',
                           help='Output raw HTML instead of structured data')
        parser.add_argument('--format', choices=['json', 'html', 'text'],
                           default='text', help='Output format')
        parser.add_argument('-v', '--verbose', action='store_true',
                           help='Show detailed output')
        parser.add_argument('--no-follow', action='store_true',
                           help='Don\'t follow redirects')
        parser.add_argument('--timeout', type=int, default=10,
                           help='Request timeout in seconds')
        return parser.parse_args()

    def run(self) -> int:
        """Run the extraction."""
        if not self.args.url and not self.args.file:
            print("Error: Either URL or --file required")
            return 1

        try:
            html = self._fetch_html()
        except Exception as e:
            print(f"Error fetching content: {e}")
            return 1

        base_url = self.args.url if self.args.url else "file://"
        extractor = MenuExtractor(html, base_url)
        menus = extractor.extract()

        menus = [m for m in menus if m['item_count'] >= self.args.min_items]

        if self.args.verbose:
            print(f"Found {len(menus)} potential menus")

        if not menus:
            print("No menus found")
            return 0

        output = self._format_output(menus)

        if self.args.output:
            Path(self.args.output).write_text(output)
            print(f"Saved to {self.args.output}")
        else:
            print(output)

        return 0

    def _fetch_html(self) -> str:
        """Fetch HTML from URL or file."""
        if self.args.file:
            return Path(self.args.file).read_text()

        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; MenEx/1.0)'
        }
        response = requests.get(
            self.args.url,
            headers=headers,
            timeout=self.args.timeout,
            allow_redirects=not self.args.no_follow
        )
        response.raise_for_status()
        return response.text

    def _format_output(self, menus: list[dict]) -> str:
        """Format menus based on selected format."""
        if self.args.format == 'json':
            import json
            return json.dumps(menus, indent=2, ensure_ascii=False)

        if self.args.format == 'html':
            return '\n\n'.join(m['html'] for m in menus)

        lines = []
        for i, menu in enumerate(menus, 1):
            lines.append(f"\n{'='*60}")
            lines.append(f"Menu #{i}")
            lines.append(f"{'='*60}")
            lines.append(f"Tag: <{menu['tag']}>")
            if menu['id']:
                lines.append(f"ID: {menu['id']}")
            if menu['classes']:
                lines.append(f"Classes: {menu['classes']}")
            if menu['role']:
                lines.append(f"Role: {menu['role']}")
            if menu['aria_label']:
                lines.append(f"ARIA: {menu['aria_label']}")
            lines.append(f"Path: {menu['path']}")
            lines.append(f"Items: {menu['item_count']} | Weight: {menu['weight']:.1f}")
            lines.append("-" * 40)
            for j, item in enumerate(menu['items'], 1):
                href = item['href'][:60] + '...' if len(item['href']) > 60 else item['href']
                lines.append(f"  {j}. {item['text']}")
                if href:
                    lines.append(f"     -> {href}")

        return '\n'.join(lines)


def main():
    cli = MenuExtractorCLI()
    exit(cli.run())


if __name__ == '__main__':
    main()