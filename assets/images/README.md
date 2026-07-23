# Topic images

Optional. One folder per slugified topic for `history` and `poll`; when present,
these are used instead of AI image generation.

```
assets/images/day-in-the-life-of-a-victorian-child/01_dawn.jpg
assets/images/which-bedroom-would-you-sleep-in-the-hardest/option1.jpg
```

Without a folder and without OPENAI_API_KEY, formats fall back to styled text
cards so the pipeline never hard-fails.
