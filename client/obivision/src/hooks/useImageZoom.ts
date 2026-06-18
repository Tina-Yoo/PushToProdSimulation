import { useEffect, useRef, useState } from "react";

export function useImageZoom(active: boolean) {
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [grabbing, setGrabbing] = useState(false);

  const overlayRef = useRef<HTMLDivElement>(null);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const hasDraggedRef = useRef(false);

  useEffect(() => {
    if (!active) {
      setScale(1);
      setPosition({ x: 0, y: 0 });
      setIsDragging(false);
      setGrabbing(false);
      hasDraggedRef.current = false;
      return;
    }

    // Body scroll lock
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = "";
    };
  }, [active]);

  const handleWheel = (e: WheelEvent) => {
    e.preventDefault();
    setScale((prev) => {
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      const newScale = Math.max(1, Math.min(8, prev + delta));
      if (newScale === 1) {
        setPosition({ x: 0, y: 0 });
      }
      return newScale;
    });
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (scale <= 1) return;
    setIsDragging(true);
    setGrabbing(true);
    hasDraggedRef.current = false;
    dragStartRef.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    };
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return;
    hasDraggedRef.current = true;
    setPosition({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setGrabbing(false);
  };

  useEffect(() => {
    if (!active) return;

    const overlay = overlayRef.current;
    if (!overlay) return;

    overlay.addEventListener("wheel", handleWheel, { passive: false });
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      overlay.removeEventListener("wheel", handleWheel);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [active, isDragging, scale, position]);

  const didDrag = () => hasDraggedRef.current;

  const imageStyle: React.CSSProperties = {
    transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
    cursor: scale > 1 ? (grabbing ? "grabbing" : "grab") : "zoom-in",
    transition: isDragging ? "none" : "transform 0.2s ease",
  };

  const overlayHandlers = {};

  const imageHandlers = {
    onMouseDown: handleMouseDown,
  };

  return {
    overlayRef,
    overlayHandlers,
    imageHandlers,
    imageStyle,
    grabbing,
    didDrag,
  };
}
