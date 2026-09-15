/* Initialize image zoom and pan controls when a zoom dialog exists. */ (() => {
  const dialog = document.getElementById("zoom");
  if (!dialog) return;
  const img = dialog.querySelector("img");
  const viewport = document.createElement("div");
  viewport.className = "zoom-viewport";
  img.before(viewport);
  viewport.append(img);
  const reset = document.createElement("button");
  reset.type = "button";
  reset.textContent = "Reset zoom";
  reset.setAttribute("aria-label", "Reset image zoom");
  dialog.insertBefore(reset, viewport);
  const label = document.createElement("span");
  label.className = "zoom-level";
  dialog.insertBefore(label, viewport);
  const style = document.createElement("style");
  style.textContent =
    "#zoom{width:94vw;max-width:1500px;height:92vh;max-height:96vh;overflow:hidden;box-sizing:border-box}#zoom .zoom-viewport{position:relative;width:100%;height:calc(100% - 44px);margin-top:10px;overflow:hidden;display:flex;align-items:center;justify-content:center;background:#060708;touch-action:none;cursor:grab}#zoom .zoom-viewport:active{cursor:grabbing}#zoom .zoom-viewport img{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;transform-origin:center;user-select:none;pointer-events:none;display:block}#zoom button{margin-right:10px}#zoom .zoom-level{color:#96e6b3;margin-left:8px}";
  document.head.append(style);
  let scale = 1,
    x = 0,
    y = 0,
    drag = null;
  /* Apply the current image zoom and pan and update its percentage label. */
  function paint() {
    img.style.transform = `translate(${x}px,${y}px) scale(${scale})`;
    label.textContent = Math.round(scale * 100) + "%";
    img.dataset.zoom = String(scale);
  }
  /* Reset image zoom, pan, and drag state. */
  function restore() {
    scale = 1;
    x = 0;
    y = 0;
    drag = null;
    paint();
  }
  viewport.addEventListener(
    "wheel",
    /* Zoom around the pointer while keeping the scale between 100% and 800%. */ (
      e,
    ) => {
      e.preventDefault();
      const rect = viewport.getBoundingClientRect(),
        px = e.clientX - rect.left - rect.width / 2,
        py = e.clientY - rect.top - rect.height / 2;
      const next = Math.min(
          8,
          Math.max(1, scale * Math.exp(-e.deltaY * 0.002)),
        ),
        ratio = next / scale;
      x = px - (px - x) * ratio;
      y = py - (py - y) * ratio;
      scale = next;
      if (scale === 1) x = y = 0;
      paint();
    },
    {
      passive: false,
    },
  );
  viewport.addEventListener(
    "pointerdown",
    /* Start dragging with the primary pointer and retain pointer capture. */ (
      e,
    ) => {
      if (e.button !== 0) return;
      drag = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
      };
      viewport.setPointerCapture(e.pointerId);
    },
  );
  viewport.addEventListener(
    "pointermove",
    /* Pan the zoomed image using the active pointer’s movement. */ (e) => {
      if (!drag || drag.id !== e.pointerId || scale === 1) return;
      x += e.clientX - drag.x;
      y += e.clientY - drag.y;
      drag = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
      };
      paint();
    },
  );
  for (const event of ["pointerup", "pointercancel", "lostpointercapture"])
    viewport.addEventListener(
      event,
      /* End dragging when the pointer is released or capture is lost. */ () =>
        (drag = null),
    );
  reset.onclick = restore;
  viewport.ondblclick = restore;
  img.addEventListener("load", restore);
  dialog.addEventListener("close", restore);
  new MutationObserver(
    /* Reset the image when the zoom dialog opens. */ () => {
      if (dialog.open) restore();
    },
  ).observe(dialog, {
    attributes: true,
    attributeFilter: ["open"],
  });
  restore();
})();
