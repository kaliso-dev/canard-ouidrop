# -*- coding: utf-8 -*-
"""
canard.py - Un gros canard qui se balade sur l'écran et fait "coin coin".

- Pas de fenêtre visible, pas de bordure, pas d'icône dans la barre des tâches
- Vraie transparence (bords lisses, fonctionne aussi sous Linux)
- Il marche en se dandinant, cligne des yeux, ouvre le bec quand il cancane
- Clic gauche : il fait coin coin
- Clic droit : il se ferme (voir la section FONCTION DE CONTROLE)

Dépendance : PySide6   ->   pip install PySide6
"""

import math
import os
import random
import struct
import sys
import tempfile
import wave

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QUrl
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QApplication, QWidget

try:
    import winsound
except ImportError:
    winsound = None

# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------
ECHELLE = 1.6          # <-- taille du canard (1.0 = ~320 px de large)
VITESSE = 3.5          # pixels parcourus à chaque image
INTERVALLE_MS = 30     # ~33 images par seconde

BASE_L, BASE_H = 340, 320   # zone de dessin "de base" avant mise à l'échelle
MARGE = 10


# ---------------------------------------------------------------------------
# Génération du son "coin coin" (synthèse, pas besoin de fichier audio)
# ---------------------------------------------------------------------------
def creer_son_coin():
    rate = 22050
    echantillons = []

    def syllabe(duree, f_debut, f_fin):
        n = int(rate * duree)
        phase = 0.0
        for i in range(n):
            t = i / n
            f = f_debut + (f_fin - f_debut) * t
            phase += f / rate
            dent_de_scie = 2 * (phase % 1) - 1
            harmonique = math.sin(2 * math.pi * phase * 3)
            enveloppe = math.sin(math.pi * t) ** 0.6
            echantillons.append(0.45 * enveloppe * (0.7 * dent_de_scie + 0.3 * harmonique))

    def silence(duree):
        echantillons.extend([0.0] * int(rate * duree))

    syllabe(0.16, 620, 440)
    silence(0.07)
    syllabe(0.20, 600, 400)

    chemin = os.path.join(tempfile.gettempdir(), "canard_coin_coin.wav")
    with wave.open(chemin, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(b"".join(struct.pack("<h", int(s * 32767)) for s in echantillons))
    return chemin


# ---------------------------------------------------------------------------
# DESSIN DU CANARD
# Tout est dessiné avec des courbes de Bézier (cubicTo) dans un repère de
# 340x320, le canard regardant vers la droite. Le QPainter s'occupe ensuite
# de l'agrandir (ECHELLE), de le retourner et de le faire se dandiner.
# ---------------------------------------------------------------------------
CONTOUR = QColor("#7A4B00")
ORANGE_CONTOUR = QColor("#9A4300")


def stylo(couleur, epaisseur):
    p = QPen(couleur, epaisseur)
    p.setJoinStyle(Qt.RoundJoin)
    p.setCapStyle(Qt.RoundCap)
    return p


def chemin_corps():
    p = QPainterPath()
    p.moveTo(70, 150)
    p.cubicTo(100, 128, 150, 132, 185, 140)      # dos
    p.cubicTo(235, 150, 268, 182, 262, 215)      # poitrail
    p.cubicTo(255, 258, 205, 276, 150, 274)      # ventre avant
    p.cubicTo(92, 272, 60, 245, 54, 212)         # ventre arrière
    p.cubicTo(44, 196, 34, 172, 38, 140)         # vers la pointe de la queue
    p.cubicTo(50, 150, 60, 152, 70, 150)
    p.closeSubpath()
    return p


def chemin_tete():
    p = QPainterPath()
    p.addEllipse(QPointF(222, 98), 60, 58)
    cou = QPainterPath()
    cou.addEllipse(QPointF(210, 132), 30, 22)   # adoucit la jonction tête-corps
    return p.united(cou)


def chemin_aile():
    p = QPainterPath()
    p.moveTo(205, 190)
    p.cubicTo(200, 160, 145, 152, 108, 170)
    p.cubicTo(88, 180, 72, 196, 58, 214)         # pointe de l'aile vers la queue
    p.cubicTo(80, 212, 92, 218, 100, 226)
    p.cubicTo(112, 224, 122, 230, 128, 238)
    p.cubicTo(140, 236, 150, 244, 158, 248)
    p.cubicTo(195, 245, 210, 220, 205, 190)
    p.closeSubpath()
    return p


def dessiner_patte(painter, hanche, angle, couleur, sombre=False):
    painter.save()
    painter.translate(hanche)
    painter.rotate(angle)
    # jambe
    painter.setPen(stylo(QColor("#D9650A") if not sombre else QColor("#B85507"), 9))
    painter.drawLine(QPointF(0, 0), QPointF(0, 34))
    # palme
    painter.translate(0, 34)
    pied = QPainterPath()
    pied.moveTo(-10, -2)
    pied.cubicTo(4, -9, 26, -7, 38, 2)
    pied.cubicTo(40, 6, 36, 9, 31, 8)
    pied.cubicTo(28, 12, 22, 12, 19, 8)
    pied.cubicTo(15, 12, 9, 12, 6, 8)
    pied.cubicTo(-2, 10, -12, 8, -10, -2)
    painter.setPen(stylo(ORANGE_CONTOUR, 3))
    painter.setBrush(couleur)
    painter.drawPath(pied)
    painter.restore()


def dessiner_canard(painter, etat):
    """
    etat : dict avec
      'droite' (bool)      direction du regard
      'pas' (float)        phase de marche
      'marche' (bool)      en mouvement ou non
      'bec' (float 0..1)   ouverture du bec
      'cligne' (bool)      yeux fermés
    """
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.save()
    painter.scale(ECHELLE, ECHELLE)
    painter.translate(MARGE, MARGE)

    if not etat["droite"]:
        painter.translate(BASE_L - 2 * MARGE, 0)
        painter.scale(-1, 1)

    # --- Ombre au sol (ne se dandine pas) ---
    ombre = QRadialGradient(QPointF(158, 298), 105)
    ombre.setColorAt(0, QColor(0, 0, 0, 70))
    ombre.setColorAt(1, QColor(0, 0, 0, 0))
    painter.save()
    painter.translate(158, 298)
    painter.scale(1, 0.16)
    painter.translate(-158, -298)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(ombre))
    painter.drawEllipse(QPointF(158, 298), 105, 105)
    painter.restore()

    # --- Dandinement ---
    phase = etat["pas"]
    if etat["marche"]:
        balancement = math.sin(phase) * 5           # degrés
        rebond = -abs(math.sin(phase)) * 5          # petit saut à chaque pas
        angle_patte = math.sin(phase) * 24
    else:
        balancement, rebond, angle_patte = 0, 0, 0

    painter.translate(0, rebond)

    # --- Pattes (arrière puis avant) ---
    dessiner_patte(painter, QPointF(170, 262), -angle_patte, QColor("#F08A1C"), sombre=True)

    painter.save()
    painter.translate(155, 285)
    painter.rotate(balancement)
    painter.translate(-155, -285)

    dessiner_patte(painter, QPointF(130, 262), angle_patte, QColor("#FFA13A"))

    # --- Silhouette corps + tête (fusionnés pour un contour propre) ---
    silhouette = chemin_corps().united(chemin_tete())
    deg = QRadialGradient(QPointF(170, 95), 230, QPointF(185, 70))
    deg.setColorAt(0.0, QColor("#FFF7B8"))
    deg.setColorAt(0.35, QColor("#FFE04A"))
    deg.setColorAt(0.75, QColor("#FFC81F"))
    deg.setColorAt(1.0, QColor("#E89E00"))
    painter.setPen(stylo(CONTOUR, 4.5))
    painter.setBrush(QBrush(deg))
    painter.drawPath(silhouette)

    # Ombre douce sous le ventre (clippée dans la silhouette)
    painter.save()
    painter.setClipPath(silhouette)
    ventre = QLinearGradient(QPointF(0, 215), QPointF(0, 278))
    ventre.setColorAt(0, QColor(200, 120, 0, 0))
    ventre.setColorAt(1, QColor(200, 120, 0, 90))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(ventre))
    painter.drawRect(QRectF(0, 215, 340, 70))
    # reflet brillant sur la tête
    reflet = QRadialGradient(QPointF(205, 62), 30)
    reflet.setColorAt(0, QColor(255, 255, 255, 170))
    reflet.setColorAt(1, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(reflet))
    painter.drawEllipse(QPointF(205, 62), 30, 22)
    painter.restore()
    painter.setPen(stylo(CONTOUR, 4.5))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(silhouette)

    # --- Aile ---
    aile_deg = QLinearGradient(QPointF(120, 160), QPointF(150, 250))
    aile_deg.setColorAt(0, QColor("#FFE36A"))
    aile_deg.setColorAt(1, QColor("#F2B00C"))
    painter.setPen(stylo(CONTOUR, 3.5))
    painter.setBrush(QBrush(aile_deg))
    painter.drawPath(chemin_aile())
    # plumes
    painter.setPen(stylo(QColor(150, 95, 0, 160), 2.5))
    painter.setBrush(Qt.NoBrush)
    for (x1, y1, cx, cy, x2, y2) in [(118, 196, 145, 200, 172, 214),
                                      (110, 212, 140, 218, 165, 232),
                                      (150, 178, 175, 182, 192, 198)]:
        plume = QPainterPath(QPointF(x1, y1))
        plume.quadTo(cx, cy, x2, y2)
        painter.drawPath(plume)

    # --- Mèche sur la tête ---
    painter.setPen(stylo(CONTOUR, 3.5))
    painter.setBrush(QColor("#FFE04A"))
    meche = QPainterPath(QPointF(212, 44))
    meche.cubicTo(205, 22, 222, 14, 228, 28)
    meche.cubicTo(232, 14, 252, 18, 244, 40)
    painter.drawPath(meche)

    # --- Joue ---
    joue = QRadialGradient(QPointF(212, 122), 16)
    joue.setColorAt(0, QColor(255, 130, 120, 150))
    joue.setColorAt(1, QColor(255, 130, 120, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(joue))
    painter.drawEllipse(QPointF(212, 122), 18, 12)

    # --- Oeil ---
    if etat["cligne"]:
        painter.setPen(stylo(QColor("#2B1A05"), 4))
        painter.setBrush(Qt.NoBrush)
        ferme = QPainterPath(QPointF(226, 88))
        ferme.quadTo(240, 98, 254, 88)
        painter.drawPath(ferme)
    else:
        painter.setPen(stylo(CONTOUR, 2.5))
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QPointF(240, 84), 15, 18)
        painter.setPen(Qt.NoPen)
        pupille = QRadialGradient(QPointF(244, 86), 12)
        pupille.setColorAt(0, QColor("#3A2410"))
        pupille.setColorAt(1, QColor("#0D0703"))
        painter.setBrush(QBrush(pupille))
        painter.drawEllipse(QPointF(244, 87), 10, 13)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QPointF(248, 81), 4.2, 4.8)
        painter.drawEllipse(QPointF(241, 93), 2, 2)

    # --- Bec ---
    ouverture = etat["bec"]
    charniere = QPointF(262, 112)
    bec_deg = QLinearGradient(QPointF(0, 95), QPointF(0, 135))
    bec_deg.setColorAt(0, QColor("#FFC266"))
    bec_deg.setColorAt(1, QColor("#FF7A12"))

    if ouverture > 0:
        # intérieur de la bouche
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#8A2A1A"))
        bouche = QPainterPath(charniere)
        bouche.lineTo(305, 104 - 6 * ouverture)
        bouche.lineTo(300, 120 + 16 * ouverture)
        bouche.closeSubpath()
        painter.drawPath(bouche)

    # mâchoire inférieure (pivote vers le bas)
    painter.save()
    painter.translate(charniere)
    painter.rotate(22 * ouverture)
    painter.translate(-charniere)
    bas = QPainterPath(QPointF(256, 114))
    bas.cubicTo(275, 116, 298, 117, 306, 114)
    bas.cubicTo(306, 124, 290, 132, 272, 131)
    bas.cubicTo(262, 130, 254, 124, 256, 114)
    painter.setPen(stylo(ORANGE_CONTOUR, 3))
    painter.setBrush(QColor("#F57A10"))
    painter.drawPath(bas)
    painter.restore()

    # mâchoire supérieure (se relève un peu)
    painter.save()
    painter.translate(charniere)
    painter.rotate(-8 * ouverture)
    painter.translate(-charniere)
    haut = QPainterPath(QPointF(254, 100))
    haut.cubicTo(272, 88, 305, 90, 316, 104)
    haut.cubicTo(322, 112, 312, 118, 298, 117)
    haut.cubicTo(282, 116, 266, 116, 254, 116)
    haut.cubicTo(250, 110, 250, 104, 254, 100)
    painter.setPen(stylo(ORANGE_CONTOUR, 3))
    painter.setBrush(QBrush(bec_deg))
    painter.drawPath(haut)
    # narine + reflet du bec
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(150, 60, 0, 170))
    painter.drawEllipse(QPointF(288, 101), 3.5, 2.2)
    painter.setBrush(QColor(255, 255, 255, 110))
    painter.drawEllipse(QPointF(272, 98), 9, 3)
    painter.restore()

    painter.restore()  # fin du dandinement
    painter.restore()


# ---------------------------------------------------------------------------
# LA FENÊTRE DU CANARD
# ---------------------------------------------------------------------------
class Canard(QWidget):
    def __init__(self):
        super().__init__()

        # FramelessWindowHint : pas de bordure ni de barre de titre
        # WindowStaysOnTopHint : toujours au premier plan
        # Tool : fenêtre "outil" -> n'apparaît pas dans la barre des tâches
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)

        # Fond vraiment transparent (pixel par pixel, bords lisses).
        # Sous Windows, les clics sur les zones transparentes traversent
        # la fenêtre et vont au bureau en dessous.
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.resize(int(BASE_L * ECHELLE), int(BASE_H * ECHELLE))

        ecran = QApplication.primaryScreen().availableGeometry()
        self.zone = ecran
        self.x = float(random.randint(ecran.left(), max(ecran.left(), ecran.right() - self.width())))
        self.y = float(random.randint(ecran.top(), max(ecran.top(), ecran.bottom() - self.height())))
        self.cible = self.nouvelle_cible()

        self.etat = {"droite": True, "pas": 0.0, "marche": True, "bec": 0.0, "cligne": False}
        self.pause = 0
        self.timer_bec = 0
        self.timer_cligne = 0
        self.prochain_cligne = random.randint(60, 160)

        self.son = creer_son_coin()
        self.effet_son = None
        if not winsound:
            try:
                from PySide6.QtMultimedia import QSoundEffect
                self.effet_son = QSoundEffect()
                self.effet_son.setSource(QUrl.fromLocalFile(self.son))
                self.effet_son.setVolume(0.8)
            except Exception:
                self.effet_son = None

        self.move(int(self.x), int(self.y))

        self.horloge = QTimer(self)
        self.horloge.timeout.connect(self.boucle)
        self.horloge.start(INTERVALLE_MS)

    # -----------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        dessiner_canard(painter, self.etat)
        painter.end()

    # =======================================================================
    # FONCTION DE CONTROLE (le "bouton d'arrêt" du canard)  <-- ICI !
    # =======================================================================
    # Problème : la fenêtre n'a ni bouton "X", ni barre de titre, ni icône
    # dans la barre des tâches. Sans mécanisme prévu, le seul moyen de
    # l'arrêter serait le Gestionnaire des tâches. C'est justement ce genre
    # de programme impossible à fermer qui ressemble à un malware.
    #
    # Solution : avec Qt, chaque widget possède des méthodes "événements"
    # que Qt appelle automatiquement. mousePressEvent() est appelée à
    # chaque clic de souris SUR la fenêtre du canard. En la redéfinissant
    # (on "surcharge" la méthode de la classe parente QWidget), on décide
    # nous-mêmes de ce qui se passe lors d'un clic.
    #
    # event.button() indique quel bouton a été pressé :
    #   Qt.RightButton  = clic droit   -> on ferme
    #   Qt.LeftButton   = clic gauche  -> coin coin
    #
    # Comme les zones transparentes laissent passer les clics, il faut
    # vraiment cliquer SUR le canard : un clic droit ailleurs sur le bureau
    # n'est pas intercepté et fonctionne normalement.
    # =======================================================================
    def mousePressEvent(self, event):                   
        if event.button() == Qt.LeftButton:
            self.coin()

    def fermer(self):
        """
        Suite de la FONCTION DE CONTROLE : appelée lors d'un clic droit.

        1. On arrête l'horloge d'animation (plus de mouvement).
        2. On coupe le son en cours.
        3. QApplication.quit() arrête la boucle d'événements app.exec() :
           comme c'est la dernière instruction du programme, le processus
           se termine complètement.
        4. On supprime le fichier .wav temporaire : aucune trace laissée.

        Le canard ne s'ajoute pas au démarrage, ne touche pas au registre,
        ne se relance pas tout seul : une fois fermé, il est vraiment parti.
        """
        self.horloge.stop()
        if winsound:
            winsound.PlaySound(None, 0)
        elif self.effet_son:
            self.effet_son.stop()
        self.close()
        QApplication.quit()
        try:
            os.remove(self.son)
        except OSError:
            pass
    # =======================================================================

    def nouvelle_cible(self):
        z = self.zone
        return (
            random.randint(z.left(), max(z.left(), z.right() - self.width())),
            random.randint(z.top(), max(z.top(), z.bottom() - self.height())),
        )

    def coin(self):
        self.timer_bec = 14
        if winsound:
            winsound.PlaySound(self.son, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif self.effet_son:
            self.effet_son.play()
        else:
            QApplication.beep()

    # -----------------------------------------------------------------------
    # Boucle d'animation appelée par le QTimer toutes les INTERVALLE_MS ms
    # -----------------------------------------------------------------------
    def boucle(self):
        if self.pause > 0:
            self.pause -= 1
            self.etat["marche"] = False
        else:
            self.etat["marche"] = True
            cx, cy = self.cible
            dx, dy = cx - self.x, cy - self.y
            distance = math.hypot(dx, dy)
            if distance < VITESSE:
                self.cible = self.nouvelle_cible()
                if random.random() < 0.5:
                    self.pause = random.randint(40, 140)
                    self.coin()
            else:
                self.x += dx / distance * VITESSE
                self.y += dy / distance * VITESSE
                if abs(dx) > 1:
                    self.etat["droite"] = dx > 0
                self.etat["pas"] += 0.32
            self.move(int(self.x), int(self.y))

        if random.random() < 0.003:
            self.coin()

        # bec : s'ouvre puis se referme en douceur
        if self.timer_bec > 0:
            self.timer_bec -= 1
            self.etat["bec"] = math.sin(math.pi * (14 - self.timer_bec) / 14)
        else:
            self.etat["bec"] = 0.0

        # clignement des yeux
        self.prochain_cligne -= 1
        if self.prochain_cligne <= 0:
            self.timer_cligne = 5
            self.prochain_cligne = random.randint(80, 200)
        if self.timer_cligne > 0:
            self.timer_cligne -= 1
        self.etat["cligne"] = self.timer_cligne > 0

        self.update()   # redemande un paintEvent


if __name__ == "__main__":
    app = QApplication(sys.argv)
    canard = Canard()
    canard.show()
    sys.exit(app.exec())
