"""
ui/forms/traj_form.py - TRAJ (Aerator Trajectory) form, v1.2.

Wired to em_traj.compute_trajectory() (faithful TRAJ.EXE engine, EM-42
App. D).  Supports the original program's workflow: load the spillway
geometry file (GLENIN format, same file as WS77), enter the ramp lip,
angle, vent geometry and flow properties, then compute the jet trajectory
(lower nappe x2 + top nappe), the air demand and the vent pressure drop.

Angle convention: positive = jet launched upward (chute deflector),
negative = descending tangent (tunnel aerator on a steep incline; the
bundled Glen Canyon reference uses -53.975 deg).
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from em_data import read_geometry_file
from em_traj import (RampGeometry, FlowProperties, VentGeometry,
                     compute_trajectory)
from ui.charts.matplotlib_widget import MplCanvas


class TRAJForm(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TRAJ - Aerator Trajectory")
        self._profile = None
        self._profile_source = ""
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)

        # -- geometry file (downstream invert profile) ------------------
        gb_geom = QtWidgets.QGroupBox("Spillway geometry (invert profile)")
        gl = QtWidgets.QFormLayout(gb_geom)
        row = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("Load geometry file...")
        self.btn_load.clicked.connect(self._load_geometry)
        self.lbl_geom = QtWidgets.QLabel("none - flat floor boundary")
        self.lbl_geom.setStyleSheet("color: #666;")
        row.addWidget(self.btn_load)
        row.addWidget(self.lbl_geom, 1)
        gl.addRow(row)
        lv.addWidget(gb_geom)

        # -- water flow properties ---------------------------------------
        gb_flow = QtWidgets.QGroupBox("Water flow properties")
        fl = QtWidgets.QFormLayout(gb_flow)
        self.q = self._spin(283.168, 0, 1e6, "%.3f")
        self.vel_ramp = self._spin(36.463, 0, 100, "%.3f")
        self.depth_ramp = self._spin(1.385, 0, 50, "%.3f")
        self.turb = self._spin(0.028, 0, 0.5, "%.4f")
        fl.addRow("Discharge Q (m^3/s):", self.q)
        fl.addRow("Mean velocity at ramp (m/s):", self.vel_ramp)
        fl.addRow("Flow depth at ramp (m):", self.depth_ramp)
        fl.addRow("Turbulence intensity T:", self.turb)
        lv.addWidget(gb_flow)

        # -- vent geometry -------------------------------------------------
        gb_vent = QtWidgets.QGroupBox("Air vent geometry")
        vl = QtWidgets.QFormLayout(gb_vent)
        self.n_vents = QtWidgets.QSpinBox()
        self.n_vents.setRange(1, 20)
        self.n_vents.setValue(2)
        self.vent_w = self._spin(1.219, 0, 20, "%.3f")
        self.vent_a = self._spin(1.486, 0, 100, "%.3f")
        self.vent_loss = self._spin(1.0, 0, 5, "%.3f")
        vl.addRow("Number of vents:", self.n_vents)
        vl.addRow("Vent width (m):", self.vent_w)
        vl.addRow("Vent area per vent (m^2):", self.vent_a)
        vl.addRow("Loss coefficient K:", self.vent_loss)
        lv.addWidget(gb_vent)

        # -- ramp geometry ---------------------------------------------------
        gb_ramp = QtWidgets.QGroupBox("Ramp geometry")
        rl = QtWidgets.QFormLayout(gb_ramp)
        self.ramp_sta = self._spin(685.80, -10000, 100000, "%.3f")
        self.ramp_elev = self._spin(1035.112, -1000, 10000, "%.3f")
        self.ramp_angle = self._spin(-53.975, -89, 89, "%.3f")
        self.ramp_angle.setToolTip(
            "Signed launch tangent angle.\n"
            "Negative = descending (tunnel aerator on steep incline,\n"
            "e.g. Glen Canyon -53.975).\n"
            "Positive = upward deflector (chute aerator).")
        self.floor_elev = self._spin(956.25, -1000, 10000, "%.3f")
        self.floor_elev.setToolTip(
            "Used only when no geometry file is loaded (flat floor).")
        rl.addRow("Ramp lip station (m):", self.ramp_sta)
        rl.addRow("Ramp lip elevation (m):", self.ramp_elev)
        rl.addRow("Launch angle (deg, +up / -down):", self.ramp_angle)
        rl.addRow("Flat floor elevation (m):", self.floor_elev)
        lv.addWidget(gb_ramp)

        btn = QtWidgets.QPushButton("Compute")
        btn.clicked.connect(self._compute)
        lv.addWidget(btn)
        lv.addStretch(1)

        # -- results panel ---------------------------------------------------
        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        self.canvas = MplCanvas(width=7, height=5, dpi=100)
        rv.addWidget(self.canvas)
        self.results = QtWidgets.QTextEdit()
        self.results.setReadOnly(True)
        self.results.setMaximumHeight(150)
        rv.addWidget(self.results)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.status = QtWidgets.QLabel(
            "Load a geometry file (optional) and click Compute.")
        layout.addWidget(self.status)

    def _spin(self, val, lo, hi, fmt):
        s = QtWidgets.QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setDecimals(4)
        return s

    # ------------------------------------------------------------------
    def _load_geometry(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open spillway geometry file", "",
            "Geometry files (*);;All files (*)")
        if not path:
            return
        try:
            g = read_geometry_file(path)
            self._profile = [(s.sta, s.invert) for s in g.stations]
            self._profile_source = path
            self.lbl_geom.setText(
                f"{g.title.strip() or path} - {len(self._profile)} stations")
            self.lbl_geom.setStyleSheet("color: #0a0;")
            if g.q > 0:
                self.q.setValue(g.q)
        except Exception as e:
            self._profile = None
            self.lbl_geom.setText(f"load failed: {e}")
            self.lbl_geom.setStyleSheet("color: #a00;")

    # ------------------------------------------------------------------
    def _compute(self):
        ramp = RampGeometry(
            angle_deg=self.ramp_angle.value(),
            elev_lip=self.ramp_elev.value(),
            sta_lip=self.ramp_sta.value(),
            elev_floor=self.floor_elev.value(),
            profile=self._profile,
            profile_source=self._profile_source,
        )
        flow = FlowProperties(
            q=self.q.value(),
            velocity_ramp=self.vel_ramp.value(),
            depth_ramp=self.depth_ramp.value(),
            turbulence=self.turb.value(),
        )
        vent = VentGeometry(
            n_vents=self.n_vents.value(),
            width=self.vent_w.value(),
            area=self.vent_a.value(),
            loss_coeff=self.vent_loss.value(),
        )
        try:
            res = compute_trajectory(ramp, flow, vent)
            if not res.success:
                self.status.setText(f"Error: {res.error_message}")
                return
            self._plot(ramp, res)
            lines = [
                f"Landing (lower nappe): STA {res.land_x:.2f}, "
                f"elev {res.land_elev:.2f}  (t = {res.land_t:.3f} s)",
                f"Air flow rate: {res.air_flow_rate:.2f} m^3/s   "
                f"(duct velocity {res.duct_velocity:.1f} m/s)",
                f"Pressure drop across vent: {res.pressure_drop_mh2o:.4f} m "
                f"H2O  (under-jet pressure "
                f"{(res.pressure_under_jet_pa - 101325.0) / 1000.0:.3f} kPa)",
                f"Cavity opening at landing: {res.cavity_opening:.3f} m   "
                f"(converged in {res.iterations} iterations)",
                f"Max top-nappe elevation: {res.max_height:.2f} m",
            ]
            if res.warnings:
                lines.append("WARNINGS: " + "; ".join(res.warnings))
            self.results.setPlainText("\n".join(lines))
            self.status.setText(
                f"Computed: landing STA {res.land_x:.1f}, "
                f"Q_air={res.air_flow_rate:.2f} m^3/s, "
                f"dP={res.pressure_drop_mh2o:.4f} m")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status.setText(f"Error: {e}")

    def _plot(self, ramp, res):
        self.canvas.fig.clear()
        ax = self.canvas.fig.add_subplot(111)

        if res.profile_used:
            px = [p[0] for p in res.profile_used]
            py = [p[1] for p in res.profile_used]
            ax.plot(px, py, "k-", linewidth=1.5, label="Invert profile")
        else:
            ax.axhline(ramp.elev_floor, color="k", linestyle="--",
                       alpha=0.5, label="Flat floor")

        ax.plot([p.x for p in res.lower_nappe],
                [p.y for p in res.lower_nappe],
                "b-", linewidth=2, label="Lower nappe (penetration)")
        ax.plot([p.x for p in res.lower_nappe_dispersed],
                [p.y for p in res.lower_nappe_dispersed],
                "b--", linewidth=1.2, label="Lower nappe (dispersion)")
        ax.plot([p.x for p in res.top_nappe],
                [p.y for p in res.top_nappe],
                "c-", linewidth=1.2, label="Top nappe")
        ax.plot(ramp.sta_lip, ramp.elev_lip, "go", markersize=9,
                label="Ramp lip")
        ax.plot(res.land_x, res.land_elev, "r*", markersize=14,
                label=f"Landing: STA {res.land_x:.1f}")

        ax.set_xlabel("Station (m)")
        ax.set_ylabel("Elevation (m)")
        ax.set_title(
            f"TRAJ v1.2: Jet Trajectory and Air Demand  "
            f"(Q_air = {res.air_flow_rate:.2f} m3/s, "
            f"dP = {res.pressure_drop_mh2o:.4f} m)")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)
        self.canvas.draw()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = TRAJForm()
    w.show()
    sys.exit(app.exec())
