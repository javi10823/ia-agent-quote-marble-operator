/**
 * Ítem de menú que abre el chat scoped enfocado en UNA pieza concreta
 * (mockup 06 · chat sobre R2 = bacha). Reusa la clase `.item` del
 * `.regen-menu` legacy para heredar el estilo del popover sin CSS nuevo.
 */
"use client";

interface Props {
  pieceId: string;
  onOpen: () => void;
}

export function PieceChatButton({ pieceId, onOpen }: Props) {
  return (
    <div
      className="item"
      role="button"
      tabIndex={0}
      data-testid={`piece-chat-${pieceId}`}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      💬 Preguntar a Valentina sobre {pieceId}
      <span className="desc">chat enfocado en esta pieza</span>
    </div>
  );
}
