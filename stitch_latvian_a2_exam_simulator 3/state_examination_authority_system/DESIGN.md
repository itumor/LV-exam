---
name: State Examination Authority System
colors:
  surface: '#f6faff'
  surface-dim: '#d2dbe4'
  surface-bright: '#f6faff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#ecf5fe'
  surface-container: '#e6eff8'
  surface-container-high: '#e0e9f2'
  surface-container-highest: '#dbe4ed'
  on-surface: '#141d23'
  on-surface-variant: '#43474f'
  inverse-surface: '#293138'
  inverse-on-surface: '#e9f2fb'
  outline: '#737780'
  outline-variant: '#c3c6d1'
  surface-tint: '#3a5f94'
  primary: '#001e40'
  on-primary: '#ffffff'
  primary-container: '#003366'
  on-primary-container: '#799dd6'
  inverse-primary: '#a7c8ff'
  secondary: '#5f5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e4e2e1'
  on-secondary-container: '#656464'
  tertiary: '#1c1f20'
  on-tertiary: '#ffffff'
  tertiary-container: '#313435'
  on-tertiary-container: '#9a9c9d'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d5e3ff'
  primary-fixed-dim: '#a7c8ff'
  on-primary-fixed: '#001b3c'
  on-primary-fixed-variant: '#1f477b'
  secondary-fixed: '#e4e2e1'
  secondary-fixed-dim: '#c8c6c6'
  on-secondary-fixed: '#1b1c1c'
  on-secondary-fixed-variant: '#474747'
  tertiary-fixed: '#e1e3e4'
  tertiary-fixed-dim: '#c5c7c8'
  on-tertiary-fixed: '#191c1d'
  on-tertiary-fixed-variant: '#454748'
  background: '#f6faff'
  on-background: '#141d23'
  surface-variant: '#dbe4ed'
typography:
  display-lg:
    fontFamily: Public Sans
    fontSize: 36px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Public Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.4'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Public Sans
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  body-md:
    fontFamily: Public Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: '0'
  label-bold:
    fontFamily: Public Sans
    fontSize: 14px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Public Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.2'
    letterSpacing: '0'
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-max-width: 1024px
  gutter: 24px
  margin-page: 48px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 32px
  stack-xl: 64px
---

## Brand & Style

This design system is engineered for the Official Latvian State Exam Simulator. The brand personality is rooted in institutional authority, reliability, and academic rigor. It prioritizes clarity and cognitive ease to ensure that the user’s mental energy is spent entirely on the examination content rather than navigating the interface.

The visual style is **Corporate / Modern** with a lean toward **Minimalism**. It utilizes a structured, high-contrast framework that mirrors the formality of physical government documents. There are no decorative flourishes; every element serves a functional purpose. The emotional response is one of serious focus, calm, and confidence in the system's stability.

## Colors

The palette is strictly functional. **Deep Navy Blue** is the anchor, used for headers, primary actions, and branding to establish a sense of officialdom. **Dark Gray** provides high legibility for body text against the **White** background.

Functional colors are reserved for feedback: **Success Green** indicates completed sections or correct submissions, while **Error Red** highlights missing fields or critical system alerts. The **Light Gray** tertiary color is utilized for background containers and subtle section dividers to maintain a structured visual hierarchy without introducing distraction.

## Typography

The design system employs **Public Sans**, an institutional typeface designed for clarity and accessibility. It provides a neutral yet authoritative tone suitable for government-led assessment.

Headlines are intentionally large and bold to clearly delineate question prompts. Body text uses a generous 1.6 line height to maximize readability during long-form reading tasks. Letter spacing is slightly tightened for large displays to maintain visual density and widened for labels to ensure quick scanning of meta-information like timers and progress percentages.

## Layout & Spacing

This design system utilizes a **Fixed Grid** model. The primary content area is constrained to a 1024px centered container to prevent excessively long line lengths, which can fatigue the eyes during an exam.

The spacing rhythm is based on a 4px baseline grid. Large vertical stacks (`stack-xl`) separate distinct exam questions, while tighter spacing (`stack-sm`) is used to group labels with their corresponding input fields. Margins are generous to create a "breathing room" effect, isolating the exam content from the browser chrome and reducing peripheral distractions.

## Elevation & Depth

To maintain a formal and flat aesthetic, this design system eschews complex shadows and blurs. It uses **Low-contrast outlines** and **Tonal layers** to establish depth.

- **Surface 0:** The primary page background (White).
- **Surface 1:** Light Gray backgrounds for secondary sidebars or progress tracking zones.
- **Outlines:** 1px solid borders in a medium-light gray (#DEE2E6) define the boundaries of cards and input fields.
- **Active State:** A subtle, low-opacity Deep Navy Blue shadow (4px blur, 10% opacity) may be applied to the "active" question card to provide a soft focus effect without appearing decorative.

## Shapes

The shape language is **Soft**, utilizing a 0.25rem (4px) base radius. This minimal rounding removes the harshness of sharp corners—making the interface feel modern and professional—while remaining sufficiently "square" to maintain a serious, governmental tone. Buttons and input fields share this consistent corner radius to create a unified component language.

## Components

### Buttons
Primary buttons use a solid Deep Navy Blue background with White text. They are high-contrast and utilize a bold font-weight. Secondary buttons use an outline style with a 1px Navy border. The "Submit" or "Finalize" action uses a Success Green background to distinguish it from standard navigation.

### Progress Bar
The progress bar is a distinct, full-width component fixed to the very top of the viewport. It uses a Light Gray track and a Deep Navy Blue fill. A numerical percentage or "Question X of Y" label is placed immediately below it for precision.

### Cards
Question cards are simple containers with 1px solid borders. They have no elevation by default. A card’s padding is generous (32px) to ensure the question text is the clear focal point.

### Form Fields
Input fields and text areas use a White background with a 1px Dark Gray border. When focused, the border thickness increases to 2px in Deep Navy Blue. Labels are always positioned above the input, never as placeholders, to ensure accessibility.

### Timer
The timer is minimalist, displayed in the top right corner. It uses a monospaced variant of the system font to prevent "jittering" as numbers change. If less than 5 minutes remain, the text color shifts to Error Red to signal urgency.

### Chips
Used for indicating question status (e.g., "Flagged for Review" or "Completed"). Chips are rectangular with a 2px radius and use muted, low-saturation versions of the functional colors to prevent them from overpowering the primary content.