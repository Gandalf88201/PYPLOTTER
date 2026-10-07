// Rotatable preview of a 3D figure while the mouse drags; the Matplotlib figure is drawn again on release.
// The projection is mplot3d's (Matplotlib Axes3D.get_proj and proj3d), so the preview lies where the
// figure will be drawn. The data come from plotting.view3d on the server.
'use strict';
(function () {
  const rad = d => d * Math.PI / 180;
  const normAngle = a => { a = ((a + 360) % 360 + 360) % 360; return a > 180 ? a - 360 : a; };
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const unit = a => { const n = Math.hypot(a[0], a[1], a[2]); return [a[0] / n, a[1] / n, a[2] / n]; };

  // (x, y, z) in data units → [fx, fy, depth, tz]: fractions of the image from its top left corner, the
  // distance along the viewing direction (more negative = farther) and mplot3d's projected z.
  function projector(v, elev, azim) {
    const [x0, x1, y0, y1, z0, z1] = v.limits;
    const box = v.box;
    const dx = (x1 - x0) / box[0], dy = (y1 - y0) / box[1], dz = (z1 - z0) / box[2];
    const R = [box[0] / 2, box[1] / 2, box[2] / 2];
    const e = rad(elev), a = rad(azim);
    const ps = [Math.cos(e) * Math.cos(a), Math.cos(e) * Math.sin(a), Math.sin(e)];
    const eye = [R[0] + v.dist * ps[0], R[1] + v.dist * ps[1], R[2] + v.dist * ps[2]];
    const V = [0, 0, Math.abs(rad(normAngle(elev))) > Math.PI / 2 ? -1 : 1];
    const w = unit(sub(eye, R));
    const u = unit(cross(V, w));
    const up = cross(w, u);
    const persp = v.focal !== null && v.focal !== undefined;
    const f = persp ? v.focal : 1;
    const E = persp ? [R[0] + v.dist * ps[0] * f, R[1] + v.dist * ps[1] * f, R[2] + v.dist * ps[2] * f] : eye;
    const A = v.affine;
    return (x, y, z) => {
      const d = [(x - x0) / dx - E[0], (y - y0) / dy - E[1], (z - z0) / dz - E[2]];
      const xv = dot(u, d), yv = dot(up, d), zv = dot(w, d);
      const px = persp ? f * xv / -zv : xv / v.dist;
      const py = persp ? f * yv / -zv : yv / v.dist;
      return [A[0] * px + A[1] * py + A[2], A[3] * px + A[4] * py + A[5], zv, persp ? v.dist / zv : -zv / v.dist];
    };
  }

  // The box of one 3D axes at a view, as mplot3d lays it out (axis3d.Axis._get_coord_info,
  // _get_axis_line_edge_points, _update_label_position): for each axis, whether the pane at its maximum
  // is the farther one (that pane is drawn, the axis line and label go on the near edges), the panes'
  // corners and where each axis label goes. Positions are [fx, fy, depth, tz] as from projector.
  const JUGGLED = [[1, 0, 2], [0, 1, 2], [0, 2, 1]];
  const TICKDIR = [1, 0, 0];             // axis3d.Axis._get_tickdir('default') with z vertical
  function layout(v, elev, azim, P = projector(v, elev, azim)) {
    const [x0, x1, y0, y1, z0, z1] = v.limits;
    const mins = [Math.min(x0, x1), Math.min(y0, y1), Math.min(z0, z1)];
    const maxs = [Math.max(x0, x1), Math.max(y0, y1), Math.max(z0, z1)];
    const lim = [[mins[0], maxs[0]], [mins[1], maxs[1]], [mins[2], maxs[2]]];
    const corner = (i, j, k) => P(lim[0][i], lim[1][j], lim[2][k]);
    const panes = [0, 1, 2].map(axis => [0, 1].map(side => {
      const pts = [];
      for (const [p, q] of [[0, 0], [0, 1], [1, 1], [1, 0]]) {
        const idx = [0, 0, 0];
        idx[axis] = side;
        idx[(axis + 1) % 3] = p;
        idx[(axis + 2) % 3] = q;
        pts.push(corner(...idx));
      }
      return { pts, tz: pts.reduce((s, c) => s + c[3], 0) / 4 };
    }));
    const highs = panes.map(([lo, hi]) => lo.tz < hi.tz);
    const minmax = highs.map((h, i) => (h ? maxs[i] : mins[i]));
    const maxmin = highs.map((h, i) => (h ? mins[i] : maxs[i]));
    const centers = mins.map((m, i) => (m + maxs[i]) / 2);
    const deltas = mins.map((m, i) => (maxs[i] - m) * 0.08);
    const away = (pos, axis, k) => pos.map((c, i) => (i === axis ? c : c + Math.sign(c - centers[i]) * deltas[i] * k));
    const edges = [0, 1, 2].map(axis => {
      const j = JUGGLED[axis];
      const e0 = minmax.slice();
      e0[j[0]] = maxmin[j[0]];
      const e1 = e0.slice();
      e1[j[1]] = maxmin[j[1]];
      return [e0, e1];
    });
    const labels = edges.map(([e0, e1], axis) => P(...away(e0.map((c, i) => (c + e1[i]) / 2), axis, v.label_shift[axis])));
    const lines = edges.map(([e0, e1]) => [P(...e0), P(...e1)]);
    // Grid lines run over the two drawn panes that contain the axis (axis3d.Axis.draw_grid); tick marks
    // and tick labels sit along the axis line (axis3d.Axis._get_updated_ticks).
    const grid = [], ticks = [];
    (v.axis || []).forEach((info, axis) => {
      const [e0] = edges[axis];
      const td = TICKDIR[axis];
      const tickdelta = highs[td] ? deltas[td] : -deltas[td];
      info.ticks.forEach((t, n) => {
        const xyz0 = minmax.slice();
        xyz0[axis] = t;
        const a = xyz0.slice(), b = xyz0.slice();
        a[(axis + 1) % 3] = maxmin[(axis + 1) % 3];
        b[(axis + 2) % 3] = maxmin[(axis + 2) % 3];
        grid.push({ axis, path: [P(...a), P(...xyz0), P(...b)] });
        const pos = e0.slice();
        pos[axis] = t;
        const out = pos.slice(), inn = pos.slice();
        out[td] = e0[td] + 0.1 * tickdelta;
        inn[td] = e0[td] - 0.2 * tickdelta;
        ticks.push({ axis, text: info.ticklabels[n], mark: [P(...out), P(...inn)], at: P(...away(pos, axis, info.tick_shift)) });
      });
    });
    return { highs, back: panes.map((p, axis) => p[highs[axis] ? 1 : 0].pts), labels, lines, grid, ticks };
  }

  // Draw every 3D axes of `data` at the given view on a canvas that covers the image exactly.
  function draw(canvas, data, elev, azim, opts = {}) {
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const scale = W / data.size_in[0] / 72;            // canvas px per point
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = data.face;                       // hides the old tick labels around the cube
    ctx.fillRect(0, 0, W, H);
    data.axes.forEach(v => {
      const P = projector(v, elev, azim);
      const toPx = q => [q[0] * W, q[1] * H, q[2], q[3]];
      const pt = (x, y, z) => toPx(P(x, y, z));
      const [bx0, by0, bx1, by1] = v.bbox;
      ctx.save();
      ctx.fillStyle = v.face;
      ctx.fillRect(bx0 * W, by0 * H, (bx1 - bx0) * W, (by1 - by0) * H);
      const box = layout(v, elev, azim, P);
      box.back.forEach((pts, axis) => {
        ctx.beginPath();
        pts.forEach((c, n) => (n ? ctx.lineTo(c[0] * W, c[1] * H) : ctx.moveTo(c[0] * W, c[1] * H)));
        ctx.closePath();
        ctx.fillStyle = v.pane[axis];
        ctx.fill();
        ctx.strokeStyle = v.edge;
        ctx.lineWidth = Math.max(0.6, 0.8 * scale);
        ctx.stroke();
      });
      const seg = (pts, color, width) => {
        ctx.beginPath();
        pts.forEach((c, n) => (n ? ctx.lineTo(c[0] * W, c[1] * H) : ctx.moveTo(c[0] * W, c[1] * H)));
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(0.5, width * scale);
        ctx.stroke();
      };
      box.grid.forEach(g => { const info = v.axis[g.axis]; if (info.grid) seg(g.path, info.grid.color, info.grid.width); });

      // Surfaces: faces sorted far to near (painter's algorithm).
      const faces = [];
      const wires = [];
      v.layers.forEach(L => {
        if (L.type === 'grid' || L.type === 'wire') {
          const at = (r, c) => { const k = r * L.cols + c; return L.z[k] === null ? null : pt(L.x[k], L.y[k], L.z[k]); };
          const grid = [];
          for (let r = 0; r < L.rows; r++) { grid.push([]); for (let c = 0; c < L.cols; c++) grid[r].push(at(r, c)); }
          if (L.type === 'grid') {
            for (let r = 0; r < L.rows - 1; r++) for (let c = 0; c < L.cols - 1; c++) {
              const q = [grid[r][c], grid[r][c + 1], grid[r + 1][c + 1], grid[r + 1][c]];
              if (q.some(p => !p)) continue;
              faces.push({ q, color: L.colors[r * (L.cols - 1) + c], depth: (q[0][2] + q[1][2] + q[2][2] + q[3][2]) / 4 });
            }
          } else {
            for (let r = 0; r < L.rows; r++) wires.push({ path: grid[r], color: L.color, width: 0.5 });
            for (let c = 0; c < L.cols; c++) wires.push({ path: grid.map(row => row[c]), color: L.color, width: 0.5 });
          }
        } else if (L.type === 'tri' || L.type === 'triwire') {
          const p = L.x.map((x, k) => (L.z[k] === null ? null : pt(x, L.y[k], L.z[k])));
          L.triangles.forEach((t, n) => {
            const q = t.map(k => p[k]);
            if (q.some(c => !c)) return;
            if (L.type === 'tri') faces.push({ q, color: L.colors[n], depth: (q[0][2] + q[1][2] + q[2][2]) / 3 });
            else wires.push({ path: [...q, q[0]], color: L.color, width: 0.4 });
          });
        }
      });
      faces.sort((a, b) => a.depth - b.depth);
      faces.forEach(f => {
        ctx.beginPath();
        f.q.forEach((c, n) => (n ? ctx.lineTo(c[0], c[1]) : ctx.moveTo(c[0], c[1])));
        ctx.closePath();
        ctx.fillStyle = f.color;
        ctx.strokeStyle = f.color;               // hides the seams between faces
        ctx.lineWidth = 0.6;
        ctx.fill();
        ctx.stroke();
      });
      const polyline = (path, color, width, alpha = 1) => {
        ctx.beginPath();
        let open = false;
        path.forEach(c => {
          if (!c) { open = false; return; }
          if (open) ctx.lineTo(c[0], c[1]); else { ctx.moveTo(c[0], c[1]); open = true; }
        });
        ctx.globalAlpha = alpha;
        ctx.strokeStyle = color;
        ctx.lineWidth = Math.max(0.5, width * scale);
        ctx.lineJoin = 'round';
        ctx.stroke();
        ctx.globalAlpha = 1;
      };
      wires.forEach(w => polyline(w.path, w.color, w.width));

      // Lines (e.g. one spectrum each in a waterfall), far ones first.
      const lines = v.layers.filter(L => L.type === 'line').map(L => {
        const path = L.x.map((x, k) => (x === null || L.y[k] === null || L.z[k] === null ? null : pt(x, L.y[k], L.z[k])));
        const ok = path.filter(Boolean);
        return { L, path, depth: ok.reduce((s, c) => s + c[2], 0) / (ok.length || 1) };
      });
      lines.sort((a, b) => a.depth - b.depth).forEach(({ L, path }) => polyline(path, L.color, L.width, L.alpha));

      // Points, far to near.
      const dots = [];
      v.layers.filter(L => L.type === 'points').forEach(L => {
        const r = Math.max(1, L.size * scale / 2);
        L.x.forEach((x, k) => {
          if (x === null || L.y[k] === null || L.z[k] === null) return;
          const c = pt(x, L.y[k], L.z[k]);
          dots.push({ c, r, color: L.colors ? L.colors[k] : L.color, alpha: L.alpha });
        });
      });
      dots.sort((a, b) => a.c[2] - b.c[2]).forEach(d => {
        ctx.globalAlpha = d.alpha;
        ctx.fillStyle = d.color;
        ctx.beginPath();
        ctx.arc(d.c[0], d.c[1], d.r, 0, 2 * Math.PI);
        ctx.fill();
      });
      ctx.globalAlpha = 1;

      // Axis names where mplot3d puts them (axis3d: _get_axis_line_edge_points, _update_label_position).
      ctx.fillStyle = v.text;
      ctx.font = `${Math.round(Math.max(9, v.label_size * scale))}px system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      box.lines.forEach((l, axis) => { if (v.axis) seg(l, v.axis[axis].line.color, v.axis[axis].line.width); });
      ctx.textBaseline = 'top';
      box.ticks.forEach(tk => {
        const info = v.axis[tk.axis];
        seg(tk.mark, info.tick_color, info.tick_width);
        if (!tk.text) return;
        ctx.fillStyle = info.tick_color;
        ctx.font = `${Math.round(Math.max(8, info.tick_size * scale))}px system-ui, sans-serif`;
        ctx.fillText(tk.text, tk.at[0] * W, tk.at[1] * H);
      });
      ctx.fillStyle = v.text;
      ctx.font = `${Math.round(Math.max(9, v.label_size * scale))}px system-ui, sans-serif`;
      ctx.textBaseline = 'middle';
      box.labels.forEach((c, axis) => {
        if (!v.labels[axis]) return;
        // A long name follows its axis line, never upside down (axis3d: art3d._norm_text_angle).
        let angle = 0;
        if (v.label_rotate && v.label_rotate[axis]) {
          const [p, q] = box.lines[axis];
          angle = Math.atan2((q[1] - p[1]) * H, (q[0] - p[0]) * W);
          if (angle > Math.PI / 2) angle -= Math.PI;
          if (angle <= -Math.PI / 2) angle += Math.PI;
        }
        ctx.save();
        ctx.translate(c[0] * W, c[1] * H);
        ctx.rotate(angle);
        ctx.fillText(v.labels[axis], 0, 0);
        ctx.restore();
      });
      ctx.restore();
    });
    (Array.isArray(data.keep) ? data.keep : []).forEach(([l, t, r, b]) => ctx.clearRect(l * W - 1, t * H - 1, (r - l) * W + 2, (b - t) * H + 2));
    if (opts.readout) {
      ctx.font = `${Math.round(11 * (opts.dpr || 1))}px system-ui, sans-serif`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      const text = opts.readout;
      const pad = 6 * (opts.dpr || 1);
      const tw = ctx.measureText(text).width;
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(pad, pad, tw + 2 * pad, 18 * (opts.dpr || 1));
      ctx.fillStyle = '#fff';
      ctx.fillText(text, 2 * pad, pad + 3 * (opts.dpr || 1));
    }
  }

  const api = { projector, layout, draw, normAngle };
  if (typeof window !== 'undefined') window.View3D = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
