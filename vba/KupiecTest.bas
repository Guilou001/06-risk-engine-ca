Attribute VB_Name = "KupiecTest"
' Le test de Kupiec en Visual Basic, pour le classeur des tests de depassement.
'
' Ce module fait le meme calcul que les formules de la feuille " Kupiec ". Il existe parce qu'une
' macro ne se fabrique pas par script : un fichier ecrit sous l'extension des classeurs a macros
' ne contient aucun projet de macros, et Excel l'ouvre comme un classeur ordinaire.
'
' Pour l'importer : Alt+F11, menu Fichier, Importer un fichier, choisir ce fichier.
' Les fonctions KUPIEC et ZONE_BALE deviennent alors disponibles dans les cellules.

Option Explicit

' La statistique du test de Kupiec.
'
' Elle compare deux vraisemblances : celle du taux de depassement promis par le modele, et celle du
' taux reellement observe. Plus l'ecart est grand, plus la statistique monte.
Public Function KUPIEC_STAT(jours As Long, depassements As Long, niveau As Double) As Double
    Dim p As Double, taux As Double, sousModele As Double, libre As Double

    If jours <= 0 Then
        KUPIEC_STAT = CVErr(xlErrValue)
        Exit Function
    End If
    If depassements < 0 Or depassements > jours Then
        KUPIEC_STAT = CVErr(xlErrValue)
        Exit Function
    End If

    p = 1# - niveau                       ' la probabilite de depassement promise
    taux = depassements / jours           ' celle qui a ete observee

    sousModele = (jours - depassements) * Log(1# - p) + depassements * Log(p)
    If depassements = 0 Then
        libre = jours * Log(1# - taux)
    ElseIf depassements = jours Then
        libre = jours * Log(taux)
    Else
        libre = (jours - depassements) * Log(1# - taux) + depassements * Log(taux)
    End If

    KUPIEC_STAT = -2# * (sousModele - libre)
End Function

' La valeur p du test : la probabilite d'observer un ecart au moins aussi grand si le modele disait
' vrai. Sous 5 %, le modele est rejete.
Public Function KUPIEC(jours As Long, depassements As Long, niveau As Double) As Variant
    Dim stat As Variant

    stat = KUPIEC_STAT(jours, depassements, niveau)
    If IsError(stat) Then
        KUPIEC = stat
    Else
        KUPIEC = Application.WorksheetFunction.ChiSq_Dist_RT(CDbl(stat), 1)
    End If
End Function

' La zone reglementaire d'une annee : vert, jaune ou rouge.
'
' Les seuils de 5 et 10 depassements valent pour 250 jours de bourse. Ils sont mis a l'echelle du
' nombre de jours reellement observes dans l'annee.
Public Function ZONE_BALE(jours As Long, depassements As Long) As String
    Dim seuilJaune As Double, seuilRouge As Double

    seuilJaune = 5# * jours / 250#
    seuilRouge = 10# * jours / 250#

    If depassements >= seuilRouge Then
        ZONE_BALE = "rouge"
    ElseIf depassements >= seuilJaune Then
        ZONE_BALE = "jaune"
    Else
        ZONE_BALE = "vert"
    End If
End Function
