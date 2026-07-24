# Estándar de commits (Conventional Commits)

Todos los commits de este repo siguen [Conventional Commits](https://www.conventionalcommits.org/).

## Formato

```
<tipo>(<alcance opcional>): <descripción en imperativo, minúsculas, ≤72 chars>

[cuerpo opcional]
```

## Tipos permitidos

| Tipo | Uso |
|---|---|
| `feat` | Nueva funcionalidad (endpoint, vista, feature del front, etc.) |
| `fix` | Corrección de bug |
| `test` | Agregar o corregir tests |
| `docs` | Solo documentación (README, CLAUDE.md) |
| `refactor` | Cambio de código que no altera comportamiento |
| `perf` | Mejora de rendimiento |
| `style` | Formato, sin cambio de lógica |
| `build` | Dependencias, empaquetado |
| `ci` | Configuración de CI/hooks |
| `chore` | Mantenimiento que no encaja en lo anterior |
| `revert` | Revertir un commit previo |

## Alcances sugeridos

En un monorepo el alcance dice dónde va el cambio: `back`, `front`, o el nombre
de la feature (`chat`, `panel`). Ejemplos:

- `feat(back): add POST /messages endpoint`
- `feat(front): chat view consuming /messages`
- `fix(back): return 422 on empty message body`
- `test(back): cover health endpoint`
- `chore: setup claude agent tooling`

## Reglas

- La primera línea NUNCA supera 72 caracteres ni termina en punto.
- Descripción en imperativo ("add", no "added" ni "adds").
- Commits pequeños y frecuentes: un cambio lógico por commit. Si un cambio toca
  backend y frontend como parte del mismo contrato (endpoint nuevo + consumo),
  puede ir en un solo commit con alcance combinado o sin alcance.
- El estándar se **fuerza** con el git hook `.claude/git-hooks/commit-msg`
  (instalado vía `git config core.hooksPath .claude/git-hooks`): un mensaje
  inválido bloquea el commit.
- Excepciones automáticas: mensajes que empiezan con `Merge`, `Revert`,
  `fixup!` o `squash!`.
