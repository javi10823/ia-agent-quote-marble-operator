"use client";

import { useState, useRef, useCallback } from "react";

interface ZoneSelectorProps {
  imageUrl: string;
  pageNum: number;
  instruction: string;
  onConfirm: (bbox: { x1: number; y1: number; x2: number; y2: number }) => void;
}

export default function ZoneSelector({
  imageUrl,
  pageNum,
  instruction,
  onConfirm,
}: ZoneSelectorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [startPoint, setStartPoint] = useState<{ x: number; y: number } | null>(null);
  const [endPoint, setEndPoint] = useState<{ x: number; y: number } | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const getNormalizedCoords = useCallback(
    (e: React.MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return { x: 0, y: 0 };
      const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
      return { x, y };
    },
    []
  );

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (confirmed) return;
      e.preventDefault();
      const coords = getNormalizedCoords(e);
      setStartPoint(coords);
      setEndPoint(coords);
      setIsDragging(true);
    },
    [confirmed, getNormalizedCoords]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging || confirmed) return;
      e.preventDefault();
      setEndPoint(getNormalizedCoords(e));
    },
    [isDragging, confirmed, getNormalizedCoords]
  );

  const handleMouseUp = useCallback(() => {
    if (!isDragging || confirmed) return;
    setIsDragging(false);
  }, [isDragging, confirmed]);

  const handleConfirm = useCallback(() => {
    if (!startPoint || !endPoint) return;
    const bbox = {
      x1: Math.min(startPoint.x, endPoint.x),
      y1: Math.min(startPoint.y, endPoint.y),
      x2: Math.max(startPoint.x, endPoint.x),
      y2: Math.max(startPoint.y, endPoint.y),
    };
    // Minimum size check (at least 5% of image)
    if (bbox.x2 - bbox.x1 < 0.05 || bbox.y2 - bbox.y1 < 0.05) return;
    setConfirmed(true);
    onConfirm(bbox);
  }, [startPoint, endPoint, onConfirm]);

  const handleReset = useCallback(() => {
    setStartPoint(null);
    setEndPoint(null);
    setIsDragging(false);
    setConfirmed(false);
  }, []);

  // Rectangle style
  const rectStyle = startPoint && endPoint ? {
    left: `${Math.min(startPoint.x, endPoint.x) * 100}%`,
    top: `${Math.min(startPoint.y, endPoint.y) * 100}%`,
    width: `${Math.abs(endPoint.x - startPoint.x) * 100}%`,
    height: `${Math.abs(endPoint.y - startPoint.y) * 100}%`,
    border: confirmed ? "3px solid #22c55e" : "3px solid #ef4444",
    backgroundColor: confirmed ? "rgba(34, 197, 94, 0.1)" : "rgba(239, 68, 68, 0.1)",
  } : undefined;

  return (
    <div className="flex flex-col gap-3 max-w-2xl">
      <p className="text-sm text-zinc-400">{instruction}</p>
      <div
        ref={containerRef}
        className="relative select-none cursor-crosshair rounded-lg overflow-hidden"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <img
          src={imageUrl}
          alt={`Página ${pageNum}`}
          className="w-full h-auto"
          draggable={false}
        />
        {rectStyle && (
          <div
            className="absolute pointer-events-none"
            style={rectStyle}
          />
        )}
      </div>
      <div className="flex gap-2">
        {startPoint && endPoint && !isDragging && !confirmed && (
          <button
            onClick={handleConfirm}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Confirmar zona
          </button>
        )}
        {startPoint && !confirmed && (
          <button
            onClick={handleReset}
            className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Reiniciar
          </button>
        )}
        {confirmed && (
          <p className="text-sm text-emerald-400">Zona confirmada. Procesando...</p>
        )}
      </div>
    </div>
  );
}
