## Resumen del PR

<!-- Qué hace este PR en 1-2 líneas -->

## Sprint y sub-branch

- Sprint: <!-- 1.5 / 2 / 3 / 4 / 5 -->
- Sub-branch: <!-- nombre del sub-branch -->
- Mergea contra: <!-- sprint-N/main o main -->

## Checklist pre-merge

### Código

- [ ] Build verde sin warnings
- [ ] Lint pass (`npm run lint`)
- [ ] Tests verdes (`npm test`)
- [ ] TypeScript strict, sin `any` salvo en boundaries documentados
- [ ] No hay credenciales, tokens, API keys ni `.env` committeados

### Si toca UI

- [ ] Tokens importados de `design_tokens.ts`, no hardcoded
- [ ] Copy en español rioplatense ("vos", "tenés", "podés")
- [ ] Animaciones con duraciones canónicas (`pulse 1.6s`, `think 2.4s`, `skel 1.4s`)
- [ ] Convención IA-celeste / Humano-púrpura respetada
- [ ] Screenshots de los mockups equivalentes adjuntos abajo
- [ ] Vercel preview deploy visible y funcional

### Si toca handoff/docs

- [ ] No se reproducen literalmente `chrome.js`, `bug-report.js` o `frame-label`
- [ ] Cifras canon Cueto-Heredia van a fixtures, no hardcodeadas en componentes

### Scope

- [ ] No se arreglan cosas fuera del scope del PR (anotadas en `docs/known-issues.md` si hay)
- [ ] No se arreglan known issues post-handoff (Master sec 20.5) sin aprobación explícita

## Screenshots / mockup reference

<!-- Para PRs de UI: screenshot del componente nuevo + screenshot del mockup HTML equivalente -->

## Notas para el auditor

<!-- Cosas que el reviewer/audit debe mirar especialmente -->
